"""Archive backfill: replay historical readings from the archive straight to Kafka.

Backfill is bulk historical data, not a live device feed, so it bypasses MQTT and produces
directly to Kafka (DESIGN.md decision 4), keyed by sensor id like the live path. It iterates the
committed study population over a date range, fetches each sensor's daily archive CSV, parses it
to canonical events, and produces them.

Usage:
    python -m sensor_reliability.replay --start 2026-09-01 --end 2026-09-07
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

import requests
from confluent_kafka import Producer

from .archive import parse_csv
from .config import Config
from .study import StudySensor, load_study_sensors

ARCHIVE_BASE = "https://archive.sensor.community"


def _dates(start: str, end: str) -> list[str]:
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def archive_url(date: str, sensor: StudySensor) -> str:
    return f"{ARCHIVE_BASE}/{date}/{date}_{sensor.archive_type}_sensor_{sensor.sensor_id}.csv"


def fetch_csv(
    date: str, sensor: StudySensor, user_agent: str, session: requests.Session
) -> str | None:
    """Return the CSV text, or None if the archive has no file for that sensor/day (404)."""
    resp = session.get(
        archive_url(date, sensor), headers={"User-Agent": user_agent}, timeout=60
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def run(cfg: Config, start: str, end: str) -> int:
    producer = Producer({"bootstrap.servers": cfg.kafka_bootstrap})
    session = requests.Session()
    sensors = load_study_sensors()
    fetched_at = dt.datetime.now(dt.timezone.utc)

    total = 0
    for date in _dates(start, end):
        day_count = 0
        for sensor in sensors:
            text = fetch_csv(date, sensor, cfg.user_agent, session)
            if text is None:
                continue
            for event in parse_csv(text, fetched_at):
                producer.produce(
                    cfg.kafka_topic, key=str(event["sensor_id"]), value=json.dumps(event)
                )
                day_count += 1
            producer.poll(0)
        producer.flush()
        total += day_count
        print(f"{date}: produced {day_count} events")
    print(f"total: {total} events -> {cfg.kafka_topic}")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay archive data to Kafka.")
    parser.add_argument("--start", required=True, help="first day, YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="last day, YYYY-MM-DD (inclusive)")
    args = parser.parse_args()
    run(Config.from_env(), args.start, args.end)


if __name__ == "__main__":
    main()

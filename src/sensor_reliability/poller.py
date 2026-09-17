"""Poll the Sensor.Community filter API for the configured area.

Two sinks:
  --sink parquet  write raw long-format rows to data/raw (M1 exploration / DQ profiling)
  --sink mqtt     publish one canonical event per reading to MQTT (the live ingestion path)

Usage:
    python -m sensor_reliability.poller --sink mqtt          # loop at POLL_INTERVAL_SECONDS
    python -m sensor_reliability.poller --sink parquet --once
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pandas as pd
import requests

from .config import Config
from .events import record_to_event
from .sensor_community import fetch_area, flatten


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def write_raw(records: list[dict], raw_dir: str, fetched_at: dt.datetime) -> Path | None:
    """Write one poll's flattened rows to data/raw/date=YYYY-MM-DD/part-<timestamp>.parquet."""
    rows = flatten(records, fetched_at)
    if not rows:
        return None
    day_dir = Path(raw_dir) / f"date={fetched_at:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"part-{fetched_at:%Y%m%dT%H%M%SZ}.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def publish_events(
    client: mqtt.Client, records: list[dict], fetched_at: dt.datetime, topic_prefix: str
) -> int:
    """Publish one event per reading to sc/<area>/<sensor_id> at QoS 1. Returns count sent."""
    sent = 0
    for rec in records:
        event = record_to_event(rec, fetched_at)
        if event is None:
            continue
        client.publish(f"{topic_prefix}/{event['sensor_id']}", json.dumps(event), qos=1)
        sent += 1
    return sent


def _connect_mqtt(cfg: Config) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sc-poller")
    client.connect(cfg.mqtt_host, cfg.mqtt_port)
    client.loop_start()
    return client


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll Sensor.Community.")
    parser.add_argument("--sink", choices=("parquet", "mqtt"), default="parquet")
    parser.add_argument("--once", action="store_true", help="fetch a single time and exit")
    args = parser.parse_args()

    cfg = Config.from_env()
    session = requests.Session()
    client = _connect_mqtt(cfg) if args.sink == "mqtt" else None

    try:
        while True:
            fetched_at = _now_utc()
            records = fetch_area(
                cfg.area_lat, cfg.area_lon, cfg.area_radius_km, cfg.user_agent, session=session
            )
            if args.sink == "mqtt":
                n = publish_events(client, records, fetched_at, cfg.mqtt_topic_prefix)
                print(f"{fetched_at:%Y-%m-%d %H:%M:%SZ} published {n} events to MQTT")
            else:
                path = write_raw(records, cfg.raw_dir, fetched_at)
                print(f"{fetched_at:%Y-%m-%d %H:%M:%SZ} records={len(records)} -> {path}")
            if args.once:
                break
            time.sleep(cfg.poll_interval_seconds)
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    main()

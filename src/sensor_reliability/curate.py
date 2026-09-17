"""Batch reprocessor: archive CSVs -> curated Parquet, reusing the streaming transforms.

The streaming job (job.py) is the live/continuous path and reads from Kafka. This is its batch
twin: it reads the archive directly and applies the *same* transforms in one bounded pass, so it
needs no Kafka/MQTT. Because both drivers share transforms.py, they produce identical curated
output; this one is what CI and the analysis use to reproduce headline results without standing
up the broker. See DESIGN.md decision 13.

    python -m sensor_reliability.curate --start 2026-09-01 --end 2026-09-13
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os

import requests
from pyspark.sql import SparkSession

from .archive import parse_csv
from .config import Config
from .replay import fetch_csv
from .streaming.transforms import (
    curated_by_location,
    dedup,
    dq_metrics,
    filter_outdoor,
    parse_events,
    with_dq_reason,
)
from .study import load_study_sensors


def collect_events(start: str, end: str, user_agent: str) -> list[dict]:
    """Fetch and parse every study sensor's archive file across the date range."""
    session = requests.Session()
    fetched_at = dt.datetime.now(dt.UTC)
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    sensors = load_study_sensors()

    events: list[dict] = []
    for i in range((d1 - d0).days + 1):
        date = (d0 + dt.timedelta(days=i)).isoformat()
        for sensor in sensors:
            text = fetch_csv(date, sensor, user_agent, session)
            if text is not None:
                events.extend(parse_csv(text, fetched_at))
    return events


def run(start: str, end: str) -> None:
    cfg = Config.from_env()
    events = collect_events(start, end, cfg.user_agent)
    print(f"collected {len(events)} events for {start}..{end}")

    spark = (
        SparkSession.builder.appName("sc-curate")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    kafka_like = spark.createDataFrame([(json.dumps(e),) for e in events], ["value"])
    long = dedup(with_dq_reason(filter_outdoor(parse_events(kafka_like))))

    window = os.environ.get("STREAM_WINDOW", "1 hour")
    curated_dir = os.environ.get("CURATED_DIR", "data/curated")
    curated_by_location(long, window).write.mode("overwrite").partitionBy("date").parquet(
        f"{curated_dir}/hourly"
    )
    dq_metrics(long, window).write.mode("overwrite").partitionBy("date").parquet(
        f"{curated_dir}/dq_metrics"
    )
    print(f"wrote curated Parquet to {curated_dir}/{{hourly,dq_metrics}}")
    spark.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess archive data to curated Parquet.")
    parser.add_argument("--start", required=True, help="first day, YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="last day, YYYY-MM-DD (inclusive)")
    args = parser.parse_args()
    run(args.start, args.end)


if __name__ == "__main__":
    main()

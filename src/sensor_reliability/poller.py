"""Poll the Sensor.Community filter API for the configured area and write raw readings to Parquet.

At this milestone the poller writes directly to Parquet, for exploration and data-quality
profiling. Republishing to MQTT (the live ingestion path) is added in M2.

Usage:
    python -m sensor_reliability.poller --once     # single fetch
    python -m sensor_reliability.poller            # loop at POLL_INTERVAL_SECONDS
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import pandas as pd
import requests

from .config import Config
from .sensor_community import fetch_area, flatten


def poll_once(cfg: Config, session: requests.Session) -> pd.DataFrame:
    fetched_at = dt.datetime.now(dt.timezone.utc)
    records = fetch_area(
        cfg.area_lat, cfg.area_lon, cfg.area_radius_km, cfg.user_agent, session=session
    )
    return pd.DataFrame(flatten(records, fetched_at))


def write_raw(df: pd.DataFrame, raw_dir: str, fetched_at: dt.datetime) -> Path:
    """Write one poll's rows to data/raw/date=YYYY-MM-DD/part-<timestamp>.parquet."""
    day_dir = Path(raw_dir) / f"date={fetched_at:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"part-{fetched_at:%Y%m%dT%H%M%SZ}.parquet"
    df.to_parquet(path, index=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll Sensor.Community and capture raw readings.")
    parser.add_argument("--once", action="store_true", help="fetch a single time and exit")
    args = parser.parse_args()

    cfg = Config.from_env()
    session = requests.Session()

    while True:
        df = poll_once(cfg, session)
        if df.empty:
            print("no records returned")
        else:
            fetched_at = df["fetched_at"].iloc[0]
            path = write_raw(df, cfg.raw_dir, fetched_at)
            print(
                f"{fetched_at:%Y-%m-%d %H:%M:%SZ} "
                f"records={df['record_id'].nunique()} rows={len(df)} -> {path}"
            )
        if args.once:
            break
        time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    main()

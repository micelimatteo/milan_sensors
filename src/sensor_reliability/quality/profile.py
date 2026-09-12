"""Data-quality profiling over captured raw readings.

Reads the Parquet written by the poller and prints a plain-text report: coverage, the
co-located PM+humidity node count (the gate for the humidity analysis), range violations,
saturated-humidity flags, and reporting-interval statistics. It measures data quality; it does
not modify or filter the data.

Usage:
    python -m sensor_reliability.quality.profile [data/raw]
"""

from __future__ import annotations

import sys

import pandas as pd

from .rules import in_plausible_range, is_outdoor, is_saturated_humidity
from ..sensor_community import PM_VALUE_TYPES


def load(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["event_time"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


def colocated_nodes(df: pd.DataFrame) -> set[int]:
    """Outdoor locations that report both PM and humidity."""
    outdoor = df[df["indoor"].apply(is_outdoor)]
    has_pm = set(outdoor.loc[outdoor["value_type"].isin(PM_VALUE_TYPES), "location_id"])
    has_hum = set(outdoor.loc[outdoor["value_type"] == "humidity", "location_id"])
    return has_pm & has_hum


def reporting_interval_seconds(df: pd.DataFrame) -> pd.Series:
    """Median gap between consecutive event times, per sensor (needs >1 distinct timestamp)."""
    gaps = []
    for _, g in df.dropna(subset=["event_time"]).groupby("sensor_id"):
        times = g["event_time"].drop_duplicates().sort_values()
        if len(times) > 1:
            gaps.extend(times.diff().dropna().dt.total_seconds().tolist())
    return pd.Series(gaps, dtype="float64")


def profile(path: str) -> None:
    df = load(path)
    records = df.drop_duplicates("record_id")

    print(f"source: {path}")
    print(f"polls (distinct fetched_at): {df['fetched_at'].nunique()}")
    if df["event_time"].notna().any():
        print(f"event-time span: {df['event_time'].min()} .. {df['event_time'].max()}")
    print(f"rows: {len(df)}  records: {len(records)}  "
          f"sensors: {df['sensor_id'].nunique()}  locations: {df['location_id'].nunique()}")

    indoor = records["indoor"]
    print(f"records outdoor: {(indoor == 0).sum()}  indoor: {(indoor == 1).sum()}  "
          f"unknown: {indoor.isna().sum()}")
    print(f"records missing coordinates: "
          f"{records[['latitude', 'longitude']].isna().any(axis=1).sum()}")

    print("\nsensor types (distinct sensors):")
    for name, n in (records.groupby("sensor_type")["sensor_id"].nunique()
                    .sort_values(ascending=False).items()):
        print(f"  {name:<16} {n}")

    nodes = colocated_nodes(df)
    print(f"\nco-located outdoor PM+humidity nodes: {len(nodes)}")

    print("\nvalue ranges (outdoor rows):")
    outdoor = df[df["indoor"].apply(is_outdoor)]
    for vt in ("P1", "P2", "temperature", "humidity", "pressure"):
        sub = outdoor[outdoor["value_type"] == vt]
        if sub.empty:
            continue
        present = sub[sub["value"].notna()]
        missing = len(sub) - len(present)
        # out-of-range is counted among present values only; missing is reported separately.
        invalid = int((~present["value"].apply(lambda v: in_plausible_range(vt, v))).sum())
        print(f"  {vt:<12} n={len(sub):<5} min={present['value'].min():<9.2f} "
              f"max={present['value'].max():<10.2f} missing={missing} out-of-range={invalid}")

    hum = outdoor[outdoor["value_type"] == "humidity"]["value"]
    print(f"\nsaturated humidity readings (>=99% RH): {hum.apply(is_saturated_humidity).sum()} "
          f"of {hum.notna().sum()}")

    gaps = reporting_interval_seconds(df)
    if gaps.empty:
        print("\nreporting interval: n/a (need multiple polls over time)")
    else:
        print(f"\nreporting interval (s): p50={gaps.median():.0f} "
              f"p90={gaps.quantile(0.9):.0f} max={gaps.max():.0f}")


def main() -> None:
    profile(sys.argv[1] if len(sys.argv) > 1 else "data/raw")


if __name__ == "__main__":
    main()

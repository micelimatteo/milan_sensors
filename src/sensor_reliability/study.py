"""The study population: the fixed set of outdoor Milan sensors used for backfill.

The archive is addressed per sensor, so replay needs an explicit sensor list. Committing that
list (config/milan_sensors.csv) makes the study population reproducible and explicit rather than
"whatever the API returned that day". It is built from captured live polls, keeping only
outdoor sensors of the types this project uses.

    python -m sensor_reliability.study --build data/raw   # regenerate the CSV
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

# Sensor types we study: PM (SDS011, SPS30, PMS5003) and climate with humidity (BME280, DHT22).
STUDY_SENSOR_TYPES = ("SDS011", "SPS30", "PMS5003", "BME280", "DHT22")

DEFAULT_STUDY_PATH = "config/milan_sensors.csv"
_FIELDS = ("sensor_id", "sensor_type", "location_id", "lat", "lon")


@dataclass(frozen=True)
class StudySensor:
    sensor_id: int
    sensor_type: str
    location_id: int
    lat: float
    lon: float

    @property
    def archive_type(self) -> str:
        """Sensor type as it appears in archive filenames (lowercase)."""
        return self.sensor_type.lower()


def load_study_sensors(path: str = DEFAULT_STUDY_PATH) -> list[StudySensor]:
    with open(path, newline="") as f:
        return [
            StudySensor(
                sensor_id=int(r["sensor_id"]),
                sensor_type=r["sensor_type"],
                location_id=int(r["location_id"]),
                lat=float(r["lat"]),
                lon=float(r["lon"]),
            )
            for r in csv.DictReader(f)
        ]


def build_from_raw(raw_dir: str, out_path: str = DEFAULT_STUDY_PATH) -> int:
    """Derive the study population from captured raw polls and write the CSV."""
    import pandas as pd

    df = pd.read_parquet(raw_dir)
    outdoor = df[(df["indoor"] == 0) & (df["sensor_type"].isin(STUDY_SENSOR_TYPES))]
    sensors = (
        outdoor.groupby(["sensor_id", "sensor_type", "location_id"], as_index=False)
        .agg(lat=("latitude", "first"), lon=("longitude", "first"))
        .sort_values(["sensor_type", "sensor_id"])
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_FIELDS)
        for row in sensors.itertuples(index=False):
            writer.writerow(
                [row.sensor_id, row.sensor_type, row.location_id, row.lat, row.lon]
            )
    return len(sensors)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the study population CSV from raw polls.")
    parser.add_argument("--build", metavar="RAW_DIR", default="data/raw")
    parser.add_argument("--out", default=DEFAULT_STUDY_PATH)
    args = parser.parse_args()
    n = build_from_raw(args.build, args.out)
    print(f"wrote {n} sensors to {args.out}")


if __name__ == "__main__":
    main()

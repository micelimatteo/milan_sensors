"""Parse Sensor.Community archive CSVs into the canonical reading event.

Archive files (https://archive.sensor.community/<date>/<date>_<type>_sensor_<id>.csv) are
semicolon-separated, one row per reading, with a common prefix
(sensor_id;sensor_type;location;lat;lon;timestamp) followed by per-sensor-type value columns.
We keep only the value types in the wire contract; the rest (durP1, ratioP1, particle counts,
altitude, sea-level pressure, ...) are ignored.

The archive carries no indoor flag. We only replay sensors from the committed outdoor study
population (config/milan_sensors.csv, derived from live metadata), so events are stamped
indoor=0 here; the guarantee comes from that selection, not from the row. See DESIGN.md.
"""

from __future__ import annotations

import datetime as dt

from .coerce import to_float, to_int
from .events import SCHEMA, WIRE_VALUE_TYPES, to_iso_z


def parse_csv(text: str, fetched_at: dt.datetime) -> list[dict]:
    lines = text.splitlines()
    if not lines:
        return []
    header = lines[0].split(";")
    events = []
    for line in lines[1:]:
        if not line:
            continue
        row = dict(zip(header, line.split(";")))
        event = row_to_event(row, fetched_at)
        if event is not None:
            events.append(event)
    return events


def row_to_event(row: dict[str, str], fetched_at: dt.datetime) -> dict | None:
    sensor_id = to_int(row.get("sensor_id"))
    if sensor_id is None:
        return None
    values = {
        vt: to_float(row[vt])
        for vt in WIRE_VALUE_TYPES
        if row.get(vt) not in (None, "")
    }
    return {
        "schema": SCHEMA,
        "source": "archive",
        "record_id": None,  # the archive has no per-reading id
        "sensor_id": sensor_id,
        "sensor_type": row.get("sensor_type"),
        "location_id": to_int(row.get("location")),
        "latitude": to_float(row.get("lat")),
        "longitude": to_float(row.get("lon")),
        "altitude": None,
        "country": None,
        "indoor": 0,  # study population is outdoor by construction (see module docstring)
        "exact_location": None,
        "timestamp": _ensure_z(row.get("timestamp")),
        "fetched_at": to_iso_z(fetched_at),
        "values": values,
    }


def _ensure_z(ts: str | None) -> str | None:
    """Archive timestamps are naive ISO in UTC; append Z if no timezone is present."""
    if not ts:
        return None
    if ts.endswith("Z") or "+" in ts:
        return ts
    return ts + "Z"

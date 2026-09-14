"""The canonical reading event: the single message contract shared by both ingestion paths.

Both the live path (API -> MQTT -> bridge -> Kafka) and the backfill path (archive CSV ->
Kafka) emit this shape, so everything downstream (the Spark job in M3) parses one schema. One
event is one reading from one sensor at one instant, with its measured values collapsed into a
`values` map.

Only the value types this project analyses are carried on the wire (PM and the climate
variables). Everything else the sources emit (noise, particle counts, derived sea-level
pressure, ...) is dropped at this boundary; that scoping is recorded in DESIGN.md.
"""

from __future__ import annotations

import datetime as dt

from .coerce import to_float, to_int

SCHEMA = "sc.reading.v1"

# Carried on the wire. P1 = PM10, P2 = PM2.5 (both micrograms per cubic metre).
WIRE_VALUE_TYPES = ("P1", "P2", "temperature", "humidity", "pressure")


def record_to_event(rec: dict, fetched_at: dt.datetime) -> dict | None:
    """Build an event from a live API record. Returns None if it has no usable sensor id."""
    sensor = rec.get("sensor") or {}
    sensor_id = to_int(sensor.get("id"))
    if sensor_id is None:
        return None
    loc = rec.get("location") or {}
    values = {
        sdv.get("value_type"): to_float(sdv.get("value"))
        for sdv in rec.get("sensordatavalues") or []
        if sdv.get("value_type") in WIRE_VALUE_TYPES
    }
    return {
        "schema": SCHEMA,
        "source": "live",
        "record_id": to_int(rec.get("id")),
        "sensor_id": sensor_id,
        "sensor_type": (sensor.get("sensor_type") or {}).get("name"),
        "location_id": to_int(loc.get("id")),
        "latitude": to_float(loc.get("latitude")),
        "longitude": to_float(loc.get("longitude")),
        "altitude": to_float(loc.get("altitude")),
        "country": loc.get("country"),
        "indoor": to_int(loc.get("indoor")),
        "exact_location": to_int(loc.get("exact_location")),
        "timestamp": _api_timestamp_to_iso(rec.get("timestamp")),
        "fetched_at": to_iso_z(fetched_at),
        "values": values,
    }


def to_iso_z(t: dt.datetime) -> str:
    """Format a datetime as UTC ISO 8601 with a trailing Z."""
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _api_timestamp_to_iso(ts: str | None) -> str | None:
    """The live API uses 'YYYY-MM-DD HH:MM:SS' (UTC); normalise to ISO with a Z."""
    if not ts:
        return None
    return ts.replace(" ", "T") + "Z"

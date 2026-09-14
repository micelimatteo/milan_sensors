"""Client for the Sensor.Community HTTP filter API, plus flattening to tabular rows.

The filter endpoint returns the readings of the last ~5 minutes for sensors within a radius of
a point. Each returned record is one reading from one sensor at one location and may carry
several measured values (e.g. a BME280 reports temperature, humidity and pressure together).
We flatten to long format: one row per (record, value_type).

Data source: Sensor.Community (https://sensor.community). Database licensed under ODbL 1.0,
contents under DbCL 1.0. See DESIGN.md decision 8.
"""

from __future__ import annotations

import datetime as dt

import requests

from .coerce import to_float, to_int

BASE_URL = "https://data.sensor.community"
_FILTER_PATH = "/airrohr/v1/filter/area={lat},{lon},{radius}"

# Value types this project uses; anything else (noise_*, pressure_at_sealevel, ...) is carried
# through by flatten() but ignored by the analysis.
PM_VALUE_TYPES = ("P1", "P2")  # P1 = PM10, P2 = PM2.5 (micrograms per cubic metre)
CLIMATE_VALUE_TYPES = ("temperature", "humidity", "pressure")


def fetch_area(
    lat: float,
    lon: float,
    radius_km: float,
    user_agent: str,
    session: requests.Session | None = None,
    timeout: float = 60.0,
) -> list[dict]:
    """Fetch the last ~5 minutes of readings within `radius_km` of (lat, lon).

    A User-Agent header is required by the API (enforced since November 2022).
    """
    url = BASE_URL + _FILTER_PATH.format(lat=lat, lon=lon, radius=radius_km)
    client = session or requests.Session()
    resp = client.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def flatten(records: list[dict], fetched_at: dt.datetime) -> list[dict]:
    """Flatten raw API records to one row per measured value.

    `fetched_at` is the poll time (UTC), kept for provenance. The per-reading `timestamp` is the
    sensor's own event time, assigned by the Sensor.Community server in UTC.
    """
    rows: list[dict] = []
    for rec in records:
        loc = rec.get("location") or {}
        sensor = rec.get("sensor") or {}
        sensor_type = (sensor.get("sensor_type") or {}).get("name")
        base = {
            "fetched_at": fetched_at,
            "record_id": rec.get("id"),
            "timestamp": rec.get("timestamp"),
            "location_id": loc.get("id"),
            "sensor_id": sensor.get("id"),
            "sensor_type": sensor_type,
            "latitude": to_float(loc.get("latitude")),
            "longitude": to_float(loc.get("longitude")),
            "altitude": to_float(loc.get("altitude")),
            "country": loc.get("country"),
            "indoor": to_int(loc.get("indoor")),
            "exact_location": to_int(loc.get("exact_location")),
        }
        for sdv in rec.get("sensordatavalues") or []:
            rows.append(
                {
                    **base,
                    "value_type": sdv.get("value_type"),
                    "value": to_float(sdv.get("value")),
                }
            )
    return rows

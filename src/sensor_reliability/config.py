"""Runtime configuration, read from the environment (and a local .env if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Settings for the poller. Values come from environment variables (see .env.example)."""

    user_agent: str
    area_lat: float
    area_lon: float
    area_radius_km: float
    poll_interval_seconds: int
    raw_dir: str = "data/raw"

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        return cls(
            user_agent=os.environ.get("SC_USER_AGENT", "sensor-reliability/0.1"),
            area_lat=float(os.environ.get("SC_AREA_LAT", "45.4642")),
            area_lon=float(os.environ.get("SC_AREA_LON", "9.1900")),
            area_radius_km=float(os.environ.get("SC_AREA_RADIUS_KM", "15")),
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "300")),
            raw_dir=os.environ.get("RAW_DIR", "data/raw"),
        )

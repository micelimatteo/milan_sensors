"""Small coercion helpers shared by the API and archive parsers.

Sensor.Community values arrive as strings (occasionally numbers, empty, or missing). These
return None on anything that will not cleanly convert, so callers never crash on bad input.
"""

from __future__ import annotations


def to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

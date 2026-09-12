"""Pure data-quality rules, kept separate from I/O so they can be unit-tested.

These are deliberately conservative: the point is to drop clearly impossible values and flag
suspicious ones, not to second-guess genuine extremes. Thresholds and their rationale are
recorded in DESIGN.md as the analysis milestones refine them.
"""

from __future__ import annotations

# Plausible physical ranges per value_type. A value outside its range is treated as invalid.
# Pressure is in pascals, as reported by the API (e.g. ~100966 Pa == ~1010 hPa).
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "P1": (0.0, 1000.0),  # PM10, ug/m3
    "P2": (0.0, 1000.0),  # PM2.5, ug/m3
    "humidity": (0.0, 100.0),  # % relative humidity
    "temperature": (-40.0, 60.0),  # deg C
    "pressure": (30_000.0, 120_000.0),  # Pa
}

# Relative humidity is physically capped at 100%, but low-cost sensors routinely report a flat
# 100% in fog or when saturated/stuck. Such readings are in-range yet suspect: they are the
# regime where optical PM sensors over-read most, so we flag rather than silently trust them.
HUMIDITY_SATURATION_THRESHOLD = 99.0


def in_plausible_range(value_type: str, value: float | None) -> bool:
    """True if `value` is within the plausible range for its type.

    Unknown value types are not range-checked here and pass through as valid.
    """
    if value is None:
        return False
    rng = PLAUSIBLE_RANGES.get(value_type)
    if rng is None:
        return True
    low, high = rng
    return low <= value <= high


def is_saturated_humidity(value: float | None) -> bool:
    """True for relative-humidity readings at or above the saturation threshold."""
    return value is not None and value >= HUMIDITY_SATURATION_THRESHOLD


def is_outdoor(indoor: int | None) -> bool:
    """Outdoor readings only. Missing/unknown indoor flags are treated as not-outdoor."""
    return indoor == 0

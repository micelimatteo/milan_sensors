"""Unit tests for the Spark transforms, run on batch DataFrames in local mode.

These require pyspark and a JVM. Where either is missing (e.g. `make test` on a host without
Java), the whole module is skipped; run it in the Spark image via `make test-spark`.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

pytest.importorskip("pyspark")

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402
from pyspark.sql import types as T  # noqa: E402

from sensor_reliability.streaming.transforms import (  # noqa: E402
    curated_by_location,
    dedup,
    filter_outdoor,
    parse_events,
    with_dq_reason,
)

LONG = T.StructType(
    [
        T.StructField("sensor_id", T.LongType()),
        T.StructField("location_id", T.LongType()),
        T.StructField("event_time", T.TimestampType()),
        T.StructField("indoor", T.IntegerType()),
        T.StructField("latitude", T.DoubleType()),
        T.StructField("longitude", T.DoubleType()),
        T.StructField("source", T.StringType()),
        T.StructField("value_type", T.StringType()),
        T.StructField("value", T.DoubleType()),
    ]
)


def _t(minute: int) -> dt.datetime:
    return dt.datetime(2026, 9, 11, 0, minute, tzinfo=dt.UTC)


@pytest.fixture(scope="session")
def spark():
    try:
        s = (
            SparkSession.builder.master("local[1]")
            .appName("tests")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.sql.shuffle.partitions", "2")
            .getOrCreate()
        )
    except Exception as e:  # no JVM available
        pytest.skip(f"Spark unavailable: {e}")
    yield s
    s.stop()


def test_parse_events_explodes_values(spark):
    events = [
        {"source": "live", "sensor_id": 1, "location_id": 10, "indoor": 0,
         "latitude": 45.4, "longitude": 9.1, "timestamp": "2026-09-11T00:10:00Z",
         "values": {"P1": 10.0, "P2": 6.0}},
        {"source": "live", "sensor_id": 2, "location_id": 10, "indoor": 0,
         "latitude": 45.4, "longitude": 9.1, "timestamp": "2026-09-11T00:12:00Z",
         "values": {"humidity": 80.0}},
    ]
    kafka = spark.createDataFrame([(json.dumps(e),) for e in events], ["value"])
    # Format event_time in the (UTC) session tz so the check does not depend on the driver's zone.
    rows = (
        parse_events(kafka)
        .select(
            "value_type",
            "value",
            F.date_format("event_time", "yyyy-MM-dd HH:mm:ss").alias("ts"),
        )
        .collect()
    )

    assert len(rows) == 3  # 2 + 1 values
    p1 = [r for r in rows if r["value_type"] == "P1"][0]
    assert p1["value"] == 10.0
    assert p1["ts"] == "2026-09-11 00:10:00"  # Z parsed as UTC


def test_filter_outdoor(spark):
    df = spark.createDataFrame(
        [(1, 10, _t(0), 0, 45.4, 9.1, "live", "P2", 6.0),
         (2, 11, _t(0), 1, 45.4, 9.1, "live", "P2", 6.0)],
        LONG,
    )
    assert {r["sensor_id"] for r in filter_outdoor(df).collect()} == {1}


def test_dq_reason_classification(spark):
    df = spark.createDataFrame(
        [(1, 10, _t(0), 0, 45.4, 9.1, "live", "P2", None),      # missing
         (1, 10, _t(1), 0, 45.4, 9.1, "live", "P2", 5000.0),    # out_of_range
         (1, 10, _t(2), 0, 45.4, 9.1, "live", "P2", 6.0),       # ok
         (2, 10, _t(3), 0, 45.4, 9.1, "live", "humidity", 150.0)],  # out_of_range
        LONG,
    )
    reasons = {(r["value_type"], r["value"]): r["dq_reason"] for r in with_dq_reason(df).collect()}
    assert reasons[("P2", None)] == "missing"
    assert reasons[("P2", 5000.0)] == "out_of_range"
    assert reasons[("P2", 6.0)] == "ok"
    assert reasons[("humidity", 150.0)] == "out_of_range"


def test_dedup_collapses_exact_duplicates(spark):
    dup = (1, 10, _t(0), 0, 45.4, 9.1, "live", "P2", 6.0)
    df = spark.createDataFrame([dup, dup, (1, 10, _t(1), 0, 45.4, 9.1, "live", "P2", 6.0)], LONG)
    assert df.count() == 3
    assert dedup(df).count() == 2  # the two identical rows collapse to one


def test_curated_colocates_pm_and_humidity(spark):
    # Two sensors at location 10 in the same hour: one PM sensor, one humidity sensor.
    rows = [
        (1, 10, _t(10), 0, 45.4, 9.1, "live", "P1", 10.0),
        (1, 10, _t(20), 0, 45.4, 9.1, "live", "P1", 20.0),  # -> mean 15
        (1, 10, _t(10), 0, 45.4, 9.1, "live", "P2", 6.0),
        (2, 10, _t(12), 0, 45.4, 9.1, "live", "humidity", 80.0),
    ]
    df = with_dq_reason(spark.createDataFrame(rows, LONG))
    result = curated_by_location(df, window="1 hour").collect()

    assert len(result) == 1
    row = result[0]
    assert row["location_id"] == 10
    assert row["pm10_mean"] == 15.0     # (10 + 20) / 2
    assert row["pm25_mean"] == 6.0
    assert row["humidity_mean"] == 80.0  # PM and humidity co-located in one row
    assert row["n_humidity"] == 1

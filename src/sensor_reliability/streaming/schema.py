"""Spark schema for the canonical wire event (sc.reading.v1). Mirrors events.py."""

from __future__ import annotations

from pyspark.sql import types as T

EVENT_SCHEMA = T.StructType(
    [
        T.StructField("schema", T.StringType()),
        T.StructField("source", T.StringType()),
        T.StructField("record_id", T.LongType()),
        T.StructField("sensor_id", T.LongType()),
        T.StructField("sensor_type", T.StringType()),
        T.StructField("location_id", T.LongType()),
        T.StructField("latitude", T.DoubleType()),
        T.StructField("longitude", T.DoubleType()),
        T.StructField("altitude", T.DoubleType()),
        T.StructField("country", T.StringType()),
        T.StructField("indoor", T.IntegerType()),
        T.StructField("exact_location", T.IntegerType()),
        T.StructField("timestamp", T.StringType()),
        T.StructField("fetched_at", T.StringType()),
        T.StructField("values", T.MapType(T.StringType(), T.DoubleType())),
    ]
)

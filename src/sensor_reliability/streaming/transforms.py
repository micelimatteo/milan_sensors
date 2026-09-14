"""Pure DataFrame transforms for the streaming job.

Kept free of Spark I/O (no readStream/writeStream) so they can be unit-tested on batch
DataFrames: the same transforms apply to streaming DataFrames in job.py. Watermarking is set by
the job, not here, because it is a streaming-only concern.

The pipeline turns one event per reading into curated per-(location, window) rows in which PM
and humidity are co-located. That co-location is the "join" at the heart of M3: PM and humidity
come from different sensors sharing a location_id, so grouping by location_id and averaging each
value type pairs them without an explicit stream-stream join. The plausible ranges are the same
ones used by the batch profiler (quality.rules), so there is a single source of truth.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from ..quality.rules import PLAUSIBLE_RANGES
from .schema import EVENT_SCHEMA

# Value types promoted to their own aggregated columns in the curated output.
_CURATED_MEANS = {
    "pm10_mean": "P1",
    "pm25_mean": "P2",
    "humidity_mean": "humidity",
    "temperature_mean": "temperature",
    "pressure_mean": "pressure",
}


def parse_events(kafka_df: DataFrame) -> DataFrame:
    """Kafka rows (a JSON string in `value`) -> one long row per (reading, value_type)."""
    event = (
        kafka_df.select(F.from_json(F.col("value").cast("string"), EVENT_SCHEMA).alias("e"))
        .select("e.*")
        # Timestamps are ISO-8601 UTC with a trailing Z; strip it and parse in the UTC session.
        .withColumn("event_time", F.to_timestamp(F.regexp_replace("timestamp", "Z$", "")))
    )
    return event.select(
        "sensor_id",
        "location_id",
        "event_time",
        "indoor",
        "latitude",
        "longitude",
        "source",
        F.explode("values").alias("value_type", "value"),
    )


def filter_outdoor(df: DataFrame) -> DataFrame:
    return df.filter(F.col("indoor") == 0)


def with_dq_reason(df: DataFrame) -> DataFrame:
    """Tag each reading: missing (null), out_of_range, or ok."""
    reason = F.when(F.col("value").isNull(), F.lit("missing"))
    for value_type, (low, high) in PLAUSIBLE_RANGES.items():
        reason = reason.when(
            (F.col("value_type") == F.lit(value_type)) & (~F.col("value").between(low, high)),
            F.lit("out_of_range"),
        )
    return df.withColumn("dq_reason", reason.otherwise(F.lit("ok")))


def dedup(df: DataFrame) -> DataFrame:
    """Collapse exact duplicates (at-least-once MQTT, API re-serving, replay overlap)."""
    return df.dropDuplicates(["sensor_id", "event_time", "value_type"])


def curated_by_location(df: DataFrame, window: str = "1 hour") -> DataFrame:
    """Per (location, event-time window): mean of each value type over the valid readings."""
    ok = df.filter(F.col("dq_reason") == F.lit("ok"))

    def mean_of(value_type: str):
        return F.avg(F.when(F.col("value_type") == F.lit(value_type), F.col("value")))

    def count_of(value_type: str):
        return F.count(F.when(F.col("value_type") == F.lit(value_type), F.col("value")))

    aggregations = [mean_of(vt).alias(name) for name, vt in _CURATED_MEANS.items()]
    aggregations += [
        count_of("P2").alias("n_pm25"),
        count_of("humidity").alias("n_humidity"),
        F.first("latitude", ignorenulls=True).alias("latitude"),
        F.first("longitude", ignorenulls=True).alias("longitude"),
    ]

    grouped = ok.groupBy(F.window("event_time", window).alias("w"), "location_id").agg(
        *aggregations
    )
    return grouped.select(
        F.col("w.start").alias("window_start"),
        F.col("w.end").alias("window_end"),
        F.to_date("w.start").alias("date"),
        "location_id",
        *_CURATED_MEANS.keys(),
        "n_pm25",
        "n_humidity",
        "latitude",
        "longitude",
    )


def dq_metrics(df: DataFrame, window: str = "1 hour") -> DataFrame:
    """Per (window, value_type, reason) reading counts: how much was kept/dropped and why."""
    grouped = df.groupBy(
        F.window("event_time", window).alias("w"), "value_type", "dq_reason"
    ).count()
    return grouped.select(
        F.col("w.start").alias("window_start"),
        F.to_date("w.start").alias("date"),
        "value_type",
        "dq_reason",
        "count",
    )

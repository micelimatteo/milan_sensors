"""Structured Streaming job: Kafka -> event-time aggregation -> curated Parquet + DQ metrics.

Runs in the pinned Spark image (see Dockerfile.spark / docker-compose). Two modes:

  --mode backfill  process all data currently in Kafka, then stop (trigger availableNow).
                   Deterministic and reproducible; used for the headline archive window.
  --mode live      keep running, processing new data on an interval.

Both use the same event-time semantics: a watermark bounds state and drops late data, exact
duplicates are removed, and readings are aggregated into per-(location, window) rows.

Absolute imports are used so the file can be launched directly with spark-submit (PYTHONPATH
points at src/).
"""

from __future__ import annotations

import argparse
import os

from pyspark.sql import DataFrame, SparkSession

from sensor_reliability.streaming.transforms import (
    curated_by_location,
    dedup,
    dq_metrics,
    filter_outdoor,
    parse_events,
    with_dq_reason,
)


def build_spark() -> SparkSession:
    return (
        SparkSession.builder.appName("sc-reliability-stream")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def read_kafka(spark: SparkSession, bootstrap: str, topic: str) -> DataFrame:
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .load()
    )


def run(mode: str) -> None:
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
    topic = os.environ.get("KAFKA_TOPIC", "sc.readings")
    curated_dir = os.environ.get("CURATED_DIR", "data/curated")
    checkpoint_dir = os.environ.get("CHECKPOINT_DIR", "data/checkpoints")
    window = os.environ.get("STREAM_WINDOW", "1 hour")
    watermark = os.environ.get("STREAM_WATERMARK", "2 hours")

    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    long = parse_events(read_kafka(spark, bootstrap, topic)).withWatermark(
        "event_time", watermark
    )
    long = dedup(with_dq_reason(filter_outdoor(long)))

    curated = curated_by_location(long, window)
    metrics = dq_metrics(long, window)

    def sink(df: DataFrame, name: str):
        writer = (
            df.writeStream.format("parquet")
            .outputMode("append")
            .partitionBy("date")
            .option("path", f"{curated_dir}/{name}")
            .option("checkpointLocation", f"{checkpoint_dir}/{name}")
        )
        if mode == "backfill":
            writer = writer.trigger(availableNow=True)
        return writer.start()

    queries = [sink(curated, "hourly"), sink(metrics, "dq_metrics")]
    for q in queries:
        q.awaitTermination()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the streaming aggregation job.")
    parser.add_argument("--mode", choices=("backfill", "live"), default="backfill")
    args = parser.parse_args()
    run(args.mode)


if __name__ == "__main__":
    main()

# Targets for the parts that exist today. Application targets (poll, replay, stream, analyze)
# are added as their milestones land.

.PHONY: up down logs install test lint fmt poll poll-once profile poll-mqtt bridge replay study \
	stream stream-live test-spark

# The Kafka connector jars are vendored into the Spark image (Dockerfile.spark), so no --packages.
SPARK_SUBMIT = /opt/spark/bin/spark-submit

up:            ## start Mosquitto + Kafka
	docker compose up -d

down:          ## stop and remove the infrastructure
	docker compose down

logs:          ## follow infrastructure logs
	docker compose logs -f

install:       ## install the package with dev dependencies (use a venv)
	pip install -e ".[dev]"

poll:          ## poll the API on a loop, writing raw Parquet to data/raw
	python -m sensor_reliability.poller

poll-once:     ## single poll, then exit
	python -m sensor_reliability.poller --once

profile:       ## data-quality profile over data/raw
	python -m sensor_reliability.quality.profile data/raw

poll-mqtt:     ## live path: poll and publish events to MQTT
	python -m sensor_reliability.poller --sink mqtt

bridge:        ## live path: forward MQTT -> Kafka
	python -m sensor_reliability.bridge

# Backfill straight to Kafka. Usage: make replay START=2026-09-01 END=2026-09-07
replay:
	python -m sensor_reliability.replay --start $(START) --end $(END)

study:         ## rebuild config/milan_sensors.csv from data/raw
	python -m sensor_reliability.study --build data/raw

stream:        ## backfill: process all Kafka data once, then stop -> data/curated
	docker compose --profile spark run --rm spark $(SPARK_SUBMIT) \
		src/sensor_reliability/streaming/job.py --mode backfill

stream-live:   ## keep processing new Kafka data
	docker compose --profile spark run --rm spark $(SPARK_SUBMIT) \
		src/sensor_reliability/streaming/job.py --mode live

test-spark:    ## run the Spark unit tests in the pinned Spark image
	docker compose --profile spark run --rm spark python3 -m pytest tests/test_streaming.py

# Batch reprocess archive -> curated Parquet without Kafka. Usage: make curate START=... END=...
curate:
	docker compose --profile spark run --rm --no-deps spark \
		python3 -m sensor_reliability.curate --start $(START) --end $(END)

analyze:       ## humidity-vs-PM analysis over data/curated -> artifacts/
	python -m sensor_reliability.analysis.humidity

reference:     ## citizen-vs-ARPA-reference comparison -> artifacts/
	python -m sensor_reliability.analysis.reference

test:
	pytest

lint:
	ruff check .

fmt:
	ruff format .

# Targets for the parts that exist today. Application targets (poll, replay, stream, analyze)
# are added as their milestones land.

.PHONY: up down logs install test lint fmt poll poll-once profile

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

test:
	pytest

lint:
	ruff check .

fmt:
	ruff format .

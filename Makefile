# Targets for the parts that exist today. Application targets (poll, replay, stream, analyze)
# are added as their milestones land.

.PHONY: up down logs install test lint fmt

up:            ## start Mosquitto + Kafka
	docker compose up -d

down:          ## stop and remove the infrastructure
	docker compose down

logs:          ## follow infrastructure logs
	docker compose logs -f

install:       ## install the package with dev dependencies (use a venv)
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

fmt:
	ruff format .

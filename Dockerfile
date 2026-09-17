# Application image for the host-side services: poller, bridge, replay. Spark has its own image
# (Dockerfile.spark). Pinned to the project's Python version.
FROM python:3.12-slim

WORKDIR /app

# Install the package (and its pinned runtime dependencies) first, for layer caching.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config ./config

# The command is supplied by docker-compose per service (poller / bridge / replay).

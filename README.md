# Citizen air-quality sensor reliability

How reliable are low-cost citizen air-quality sensors? This project takes data from
[Sensor.Community](https://sensor.community) (a global network of DIY PM/temperature/humidity
sensors) and tries to answer two concrete questions with proper data-quality accounting and
some statistical rigour:

1. **Humidity bias.** Low-cost optical PM sensors are known to over-read at high relative
   humidity (hygroscopic particle growth, and fog/condensation misread as particles). How
   large is that effect in this data, and does a simple correction reduce it?
2. **Agreement with reference stations.** How do citizen sensors compare against nearby
   reference-grade stations — not as a single "R²", but as bias and error *distributions*
   (p50/p90/p95)?

This is deliberately **not** another live air-quality map. Readers and simple API clients for
Sensor.Community already exist; the plumbing is not the contribution. The contribution is the
reliability analysis and the honest data-quality accounting that feeds it.

## Status

Under construction, milestone by milestone. What exists today: repository skeleton and the
service scaffolding (message broker + log). The ingestion, stream processing, and analysis are
being added in subsequent milestones (see `DESIGN.md` for the plan and the reasoning behind
each choice). Sections below marked *(pending)* are not implemented yet; nothing here reports
results that do not exist.

## Scope of the first slice

One city (Milan), a handful of co-located sensors, the full path working end to end with
data-quality checks and the humidity-vs-PM analysis. Reference-station comparison and any
spatial patterns come after that core is correct.

## Architecture (overview)

The data source is an HTTP JSON API that publishes per-sensor averages roughly every five
minutes. It is a **poll**, not a native stream — this project manufactures a stream by polling,
and the streaming machinery exists to get event-time processing and reprocessing right, not to
pretend the source is real-time.

```
live:     poller --MQTT--> Mosquitto --> bridge --\
                                                    +--> Kafka --> Spark Structured Streaming
backfill: archive replay ---------------------------/            (event-time, dedup, joins)
                                                                          |
                                                                          v
                                                          partitioned Parquet --> pandas analysis
```

Why MQTT *and* Kafka, and why the backfill skips MQTT, is documented in `DESIGN.md` (decisions
3 and 4) — including the candid limits of using MQTT with a single poller.

## Data source, provenance, license

- **Measurements:** Sensor.Community open API, base `https://data.sensor.community`. No API key;
  a `User-Agent` header is required. Daily CSV snapshots are archived at
  `https://archive.sensor.community`.
- **License:** Sensor.Community data is published under the Open Database License (ODbL 1.0).
  Exact attribution text and the canonical license link are pinned in `DESIGN.md` (decision 8).
- **Reference data (later milestone):** OpenAQ v3, whose European coverage originates from the
  European Environment Agency. Requires a free API key.

## Running it *(partly pending)*

Requirements: Docker and Docker Compose; Python 3.11 for local development and tests.

Bring up the infrastructure (message broker and log):

```bash
make up      # start Mosquitto + Kafka
make down    # stop and remove them
```

Install the Python package for local development and run the tests:

```bash
make install
make test
```

The ingestion, streaming, and analysis commands (`make poll`, `make replay`, `make stream`,
`make analyze`) are added as their milestones land.

## Results *(pending)*

Result artifacts (a small set of charts and tables answering the reliability question) and the
written analysis will live in `ANALYSIS.md` and an `artifacts/` directory once the analysis
milestones are complete. No results are reported until they exist.

## Limitations and next steps

Tracked honestly in `ANALYSIS.md` as findings accumulate. Known constraints going in: the
source is a 5-minute poll of already-averaged values; citizen-sensor metadata (siting, exact
coordinates) is uneven; and reference stations are sparse relative to citizen sensors.

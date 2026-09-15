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

Under construction, milestone by milestone. Working end to end today: ingestion (poller ->
MQTT -> Kafka, plus archive backfill), Spark event-time stream processing to curated Parquet, and
the humidity-vs-PM analysis with committed result artifacts (see Results). Still to come: the
reference-station comparison (M5) and containerising the app services for a single-command run
(M6). See `DESIGN.md` for the plan and the reasoning behind each choice.

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
- **License:** Sensor.Community data is published under the Open Database License (ODbL 1.0) for
  the database and the Database Contents License (DbCL 1.0) for the contents. This project
  contains data from Sensor.Community (https://sensor.community), licensed under ODbL 1.0 /
  DbCL 1.0. See `DESIGN.md` (decision 8).
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

Capture raw readings for the configured region and run the data-quality profile:

```bash
cp .env.example .env    # adjust SC_USER_AGENT with a contact address
make poll-once          # single poll -> data/raw/date=.../part-*.parquet
make profile            # data-quality report over data/raw
```

`make poll` runs the poller on a loop.

Ingestion transport (needs `make up` running). The live path publishes one canonical event per
reading to MQTT and bridges it to Kafka; the backfill path replays historical readings from the
archive straight to Kafka.

```bash
make up                                   # Mosquitto + Kafka
make bridge                               # MQTT -> Kafka (leave running)
make poll-mqtt                            # live path: poll -> MQTT (another terminal)
make replay START=2026-09-01 END=2026-09-07   # backfill -> Kafka
```

The study population that backfill iterates lives in `config/milan_sensors.csv`; regenerate it
from captured polls with `make study`.

Stream processing (Spark, runs in its pinned image under the `spark` compose profile):

```bash
make stream       # backfill: drain Kafka once, then stop -> data/curated/{hourly,dq_metrics}
make stream-live  # keep processing new data
```

`hourly` holds per-(location, hour) means with PM and humidity co-located; `dq_metrics` holds
per-window kept/dropped counts by reason.

Without Kafka, the same curated data can be produced directly from the archive (the batch twin of
the streaming job, sharing its transforms), then analysed:

```bash
make curate START=2026-09-01 END=2026-09-13   # archive -> data/curated (no broker needed)
make analyze                                  # humidity-vs-PM analysis -> artifacts/
```

### Tests

```bash
make test         # non-Spark tests (host, no Java needed)
make test-spark   # Spark transform tests, in the pinned Spark image
```

The Spark tests also run on the host if a JDK is present and the extra is installed
(`pip install -e ".[spark,dev]"`, then `make test` picks them up); without a JVM they skip.

Note: the host code and tests run on Python 3.11 or 3.12. The Spark milestone (M3) settles the
interpreter/Spark version question recorded in `DESIGN.md` (decision 9).

## Results

Part (a), humidity vs PM (Milan, 2026-09-01..2026-09-13; full write-up in `ANALYSIS.md`,
artifacts in `artifacts/`):

- Over 2473 co-located hourly rows, the marginal PM2.5-vs-RH association is weakly **negative**
  (Spearman -0.16), not positive. The relationship is dominated by **diurnal confounding**: RH
  peaks overnight while PM peaks at rush hour.
- Even at RH >= 99% (22% of rows), PM2.5 is not clearly elevated -- no clean hygroscopic inflation
  is visible in this clean September air.
- The standard kappa-Koehler correction deflates readings heavily and is **unstable near
  saturation** (95-100% RH bin median 3.30 -> ~0.07 ug/m3), so it cannot be trusted here without a
  reference.
- Practical takeaway: flag PM at high RH (>= ~90%, a third of the data) as low-confidence. Whether
  a correction actually reduces bias is answered in M5 against reference stations.

This is an honest, partly negative result: in this window the humidity artifact is not separable
from meteorology using the citizen data alone. Part (b) (reference comparison) is next.

## Limitations and next steps

Tracked honestly in `ANALYSIS.md` as findings accumulate. Known constraints going in: the
source is a 5-minute poll of already-averaged values; citizen-sensor metadata (siting, exact
coordinates) is uneven; and reference stations are sparse relative to citizen sensors.

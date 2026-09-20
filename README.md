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
MQTT -> Kafka, plus archive backfill), Spark event-time stream processing to curated Parquet, the
humidity-vs-PM analysis, the citizen-vs-reference comparison, and an optional SAREF/RDF + SPARQL
layer, all with committed result artifacts (see Results). The services are containerised and a CI
workflow runs lint and the full test suite on every push. See `DESIGN.md` for the plan and the
reasoning behind each choice.

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
- **Reference data:** ARPA Lombardia (the regional environmental agency), daily PM2.5 from its
  Milan stations, via the Socrata Open Data API (dati.lombardia.it). Keyless.

## Running it

Requirements: Docker and Docker Compose; Python 3.11 or 3.12 for host-side development, the
analysis, and tests. Copy the env template first (set a real contact address in the User-Agent):

```bash
cp .env.example .env
```

### Reproduce the results

The headline analysis needs no live services. `curate` reprocesses the archive to curated Parquet
inside the pinned Spark image (reusing the streaming transforms); the analysis runs on the host:

```bash
make install                                  # host package + dev deps
make curate START=2026-09-01 END=2026-09-13   # archive -> data/curated (Spark image, no broker)
make analyze                                  # humidity vs PM       -> artifacts/
make reference                                # citizen vs ARPA ref  -> artifacts/
```

Curated outputs: `hourly` (per-(location, hour) means, PM and humidity co-located) and
`dq_metrics` (per-window kept/dropped counts by reason).

### Live streaming pipeline (optional)

The end-to-end streaming path, containerised:

```bash
docker compose --profile live up --build   # infra + poller -> MQTT -> bridge -> Kafka
make stream                                # Spark: drain Kafka -> data/curated (another terminal)
```

Backfill through Kafka instead of the live poller: `make replay START=... END=...`. To drive the
pieces on the host rather than in containers: `make up`, then `make bridge` / `make poll-mqtt`, or
`make poll-once` / `make profile` for raw capture and the data-quality report. The study
population backfill iterates is `config/milan_sensors.csv` (regenerate with `make study`).

### Tests

```bash
make test         # host tests (the Spark tests self-skip without a JVM)
make test-spark   # Spark transform tests in the pinned Spark image
```

CI (GitHub Actions) runs ruff and the full suite on every push, with a JDK so the Spark tests
execute too.

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

Part (b), agreement with reference stations (ARPA Lombardia daily PM2.5, three Milan stations;
166 paired location-days):

- Citizen sensors **substantially under-read**: mean citizen PM2.5 4.4 vs reference 12.5 ug/m3,
  median bias **-8.3 ug/m3** (~a third of the reference). This holds for the near subset (<= 5 km,
  median bias -7.6), so it is not a distance artifact (`artifacts/citizen_vs_reference.png`).
- Absolute error vs reference (near subset, raw): p50 7.8, p90 12.5, p95 13.6 ug/m3.
- Because the sensors under-read, the humidity correction **increases** error (near p50 7.8 ->
  10.3): the standard RH correction is harmful here, not helpful.

**Overall:** the first-order reliability problem for these sensors in Milan is a large,
roughly multiplicative under-reading (a calibration/scale issue), which dwarfs the humidity
effect. The useful fix is a per-sensor scale calibration against the reference, not a blanket
humidity correction. Full write-up in `ANALYSIS.md`.

## Semantic layer (SAREF/RDF, optional)

An optional, self-contained phase models the sensors, measurements, locations and units with the
[SAREF](https://saref.etsi.org/) ontology and answers the reliability question in SPARQL. It reads
the committed `artifacts/reference_pairs.csv`, so it runs offline:

```bash
pip install -e ".[rdf]"
make graph        # builds artifacts/graph.ttl and runs the SPARQL queries
```

The mean-PM2.5-per-network query reproduces the headline straight from the graph (citizen ~4.4 vs
reference ~12 ug/m3), and a graph join of each citizen sensor to its nearest reference reproduces
the per-location bias. Design notes in `DESIGN.md` (decision 17).

## Limitations and next steps

Tracked honestly in `ANALYSIS.md` as findings accumulate. Known constraints going in: the
source is a 5-minute poll of already-averaged values; citizen-sensor metadata (siting, exact
coordinates) is uneven; and reference stations are sparse relative to citizen sensors.

## License

Code is licensed under the MIT License (`LICENSE`). The Sensor.Community measurement data is used
under ODbL 1.0 / DbCL 1.0, and the reference data is from ARPA Lombardia's open data portal.

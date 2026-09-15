# Analysis note

A short research note on the reliability of low-cost citizen PM sensors in Milan. This covers
part (a): the relationship between reported PM and humidity, and what a standard humidity
correction does. Part (b), the comparison against reference-grade stations, is M5 and not yet
written.

## Question

How does reported PM2.5 vary with relative humidity for low-cost citizen sensors, and can a
simple correction reduce the humidity-driven bias? Low-cost optical PM sensors are known to
over-read at high humidity (hygroscopic particle growth; fog droplets miscounted as particles).

## Data and window

- **Source:** Sensor.Community archive, Milan (15 km around the centre), 2026-09-01 to 2026-09-13.
- **Study population:** 22 outdoor sensors (`config/milan_sensors.csv`), of which 8 locations
  carry both a PM sensor and a humidity sensor (the co-located set the analysis needs).
- **Pipeline:** archive -> canonical events -> Spark event-time aggregation into per-(location,
  hour) means, PM and humidity co-located by shared location id -> curated Parquet -> pandas.
- **Analysis rows:** 2473 co-located hourly rows (requiring at least 3 readings behind each
  hourly mean), across the 8 co-located locations.

## Data quality

Over 380,219 outdoor readings (after dedup):

| reason | share |
|---|---|
| ok | 96.63% |
| missing (empty value) | 3.37% (all PM: P1/P2) |
| out of plausible range | 0.0005% (2 humidity readings) |

Out-of-range values are essentially absent in this window; the main loss is ~3.4% of PM
readings arriving empty. Indoor sensors and non-study sensor types were excluded upstream (by
the study population and the outdoor filter). Full per-window counts are written to
`data/curated/dq_metrics`.

## Method

- **Co-location** is a group-by on `location_id`: PM and humidity come from different sensors at
  the same node, so averaging each value type per (location, hour) pairs them.
- **Correction:** the kappa-Koehler hygroscopic growth correction (Crilley et al., 2018),
  `PM_dry = PM_wet / (1 + kappa * a_w / (1 - a_w))` with water activity `a_w = RH/100` and a
  literature `kappa = 0.5`. The value is not fitted: fitting requires a reference (M5).
- **Confounding** is examined with a diurnal decomposition (PM and RH by local hour).
- Rank correlation is Spearman.

## Findings

**1. The marginal PM2.5-vs-RH relationship is weakly negative, not positive.**
Spearman correlation is **-0.16**. Median PM2.5 by humidity bin is non-monotonic: it rises to
~4.4 ug/m3 at 40-50% RH, falls to ~1.3 at 70-80%, and rises again to ~3.3 at 95-100%
(`artifacts/pm_vs_rh.png`, `artifacts/rh_bins.csv`). This is the opposite of the naive "humidity
inflates PM" expectation.

**2. The reason is diurnal confounding.** RH peaks overnight and in the early morning (~75%) and
is lowest in the afternoon (~55%). PM2.5 peaks at the evening rush (~8.6 ug/m3 mean at 20:00) and
the morning rush, and is lowest mid-afternoon (`artifacts/diurnal_confound.png`). RH and the
human/meteorological drivers of PM move on different daily cycles, so the marginal PM-vs-RH curve
mixes a real diurnal signal with any sensor artifact.

**3. No clear hygroscopic inflation is visible in this window.** Even at RH >= 99% (22% of the
rows -- Milan is frequently foggy), PM2.5 is not clearly elevated (median ~3.4 vs ~3.3 overall).
In this clean, humid September air the humidity artifact, if present, is not separable from
meteorology using the citizen data alone.

**4. The standard correction is aggressive and unstable here.** The kappa-Koehler correction
deflates readings materially even at moderate RH, and diverges toward saturation: the 95-100% bin
median drops from 3.30 to ~0.07 ug/m3. Applied blindly it would introduce a large low bias.
Whether it improves or harms accuracy cannot be decided without a reference.

**Reliability takeaway (data-quality action):** the honest, defensible move on this dataset is to
**flag PM readings at high RH (>= ~90%, about a third of the data) as low-confidence** rather than
trust either the raw value or an unvalidated correction. High RH is where both the physical
artifact and the correction's instability live.

## Limitations

- **Confounding is not resolved.** Without a co-located reference we cannot separate a genuine
  PM-RH relationship from the sensor artifact; the diurnal structure makes the marginal
  correlation uninformative on its own.
- **Clean-air window.** September PM is low (mostly 1-6 ug/m3), so there is little signal and the
  humidity artifact -- expected to matter most when there is real PM plus fog -- is weak.
- **The correction is illustrative, not validated.** `kappa` is a literature value, and the
  correction is numerically unstable at the high RH that dominates this data.
- **Hourly aggregation** smooths sub-hourly humidity swings; **fuzzed coordinates**
  (`exact_location = 0`) limit siting precision (relevant to M5).

## Next steps

- **M5: validate against reference stations.** Compare citizen PM2.5 to nearby reference-grade
  PM2.5 (OpenAQ/EEA) and report bias and error distributions (p50/p90/p95). This is what lets us
  say whether the humidity correction actually reduces bias, and whether the high-RH flag is the
  right call.
- **A winter Po Valley window** (high PM plus persistent fog) is the condition under which the
  hygroscopic effect should be strongest; re-running the same pipeline there would test whether
  the artifact appears when there is real PM to inflate.
- **Per-location analysis** rather than pooled, to check whether some sensors show the effect
  more than others.

# Analysis note

A short research note on the reliability of low-cost citizen PM sensors in Milan. Part (a) is the
relationship between reported PM and humidity and what a standard humidity correction does; part
(b) is the comparison against reference-grade stations. The two parts together change the
headline: the dominant reliability problem here is not humidity inflation but a large systematic
under-reading relative to the reference.

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
Part (b) then shows why this matters: the sensors already *under*-read, so the deflating
correction makes accuracy **worse**, not better.

## Findings -- part (b): agreement with reference stations

Reference: ARPA Lombardia daily PM2.5 (three active Milan stations: v.Marche, v.Senato, Pascal
Citta Studi), via the Socrata API. Each citizen location is paired with its nearest station;
citizen hourly means are aggregated to daily to match the reference cadence. 166 paired
location-days (14 locations); a near subset within 5 km gives 113 location-days (9 locations).

**5. Citizen sensors substantially under-read PM2.5.** Mean citizen PM2.5 is 4.4 ug/m3 against a
reference mean of 12.5 -- the citizen daily values are roughly a third of the reference. Bias
(citizen minus reference) has median **-8.3 ug/m3** over all pairs and **-7.6 ug/m3** for the near
subset, so it is not an artefact of distant stations. Nearly every point sits below the 1:1 line
(`artifacts/citizen_vs_reference.png`).

**6. Error distributions (absolute error vs reference, ug/m3):**

| subset | p50 | p90 | p95 |
|---|---|---|---|
| all pairs, raw | 8.5 | 13.8 | 15.3 |
| near (<= 5 km), raw | 7.8 | 12.5 | 13.6 |
| near, RH-corrected | 10.3 | 15.5 | 16.7 |

**7. The humidity correction makes it worse.** Because the sensors under-read, applying the
kappa-Koehler correction (which deflates) increases the error at every percentile (near p50 7.8
-> 10.3). So for these sensors, in this regime, the standard RH correction is not just
unvalidated -- it is harmful. This is the concrete answer to part (a)'s "can a simple correction
reduce the bias?": here, no.

**Reliability takeaway.** The first-order reliability issue for these citizen sensors in Milan is
a large, roughly multiplicative under-reading against the reference (a calibration/scale problem),
which dwarfs the humidity effect. The humidity artifact, expected at high RH, is not separable
from meteorology in the citizen data alone (part a) and does not show up as a positive bias
against the reference (part b). A blanket RH correction should not be applied; the useful next
step is a per-sensor scale calibration against the reference, not a humidity correction.

## Limitations

- **Daily reference resolution.** ARPA publishes PM2.5 as daily means, so the comparison is daily;
  it cannot probe a within-day (hourly) humidity effect directly.
- **Sparse, central reference network.** Only three active Milan PM2.5 stations, all central. Some
  citizen locations are several km away, mixing sensor error with real spatial differences; the
  near-subset (<= 5 km) is reported to control for this and shows the same result.
- **Short window and clean air.** 13 days of low September PM (reference ~12 ug/m3, citizen ~4).
  Percentiles beyond p90 rest on few points; the humidity artifact -- expected mainly with high PM
  plus fog -- has little signal here.
- **Under-reading cause not diagnosed.** The ~3x gap is consistent with an uncalibrated optical
  sensor and factory scaling, but we do not attribute it; we only measure it.
- **Confounding in part (a) is unresolved by design**, and the kappa-Koehler `kappa` is a
  literature value, unstable near saturation. **Fuzzed coordinates** (`exact_location = 0`) limit
  siting precision.

## Next steps

- **Per-sensor scale calibration** against the reference (a multiplicative factor per sensor), then
  re-check the error distributions -- this is the correction the data actually calls for, not an
  RH correction.
- **A winter Po Valley window** (high PM plus persistent fog) to test whether a humidity over-read
  emerges when there is real PM to inflate, and whether it partially offsets the under-read.
- **Per-sensor analysis** rather than pooled, to see how much unit-to-unit variation there is in
  both the scale bias and any humidity sensitivity.

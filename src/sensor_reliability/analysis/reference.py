"""Citizen vs reference comparison (part b), using ARPA Lombardia as ground truth.

ARPA Lombardia is the regional environmental agency; its measurements are the official
reference-grade data for Milan (and feed the EEA). We take its PM2.5 stations, pair each citizen
location with the nearest one, and compare daily means -- reporting bias and error distributions
(p50/p90/p95), not a single number.

Constraints, stated honestly:
- ARPA publishes PM2.5 as **daily** means, so the comparison is at daily resolution.
- Milan has only three active PM2.5 reference stations, all central; distant citizen locations are
  compared across several km, which mixes sensor error with real spatial differences. We report
  the distance and also a near-only subset.

Data: ARPA Lombardia via the Socrata Open Data API (dati.lombardia.it), station registry
`ib47-atvt` and the 2026 measurements dataset `nicp-bhqi`. Keyless.

    python -m sensor_reliability.analysis.reference --start 2026-09-01 --end 2026-09-13
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from .humidity import koehler_correction  # noqa: E402

ARPA = "https://www.dati.lombardia.it/resource"
STATIONS_DATASET = "ib47-atvt"
MEASUREMENTS_DATASET = "nicp-bhqi"  # 2026 rolling; uses the registry sensor ids
PM25_TYPE = "Particelle sospese PM2.5"
LOCAL_TZ = "Europe/Rome"
NEAR_KM = 5.0  # distance under which a citizen-reference pair is treated as well co-located


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _soql(dataset: str, session: requests.Session, **params) -> list[dict]:
    resp = session.get(f"{ARPA}/{dataset}.json", params=params, timeout=60,
                       headers={"User-Agent": "sensor-reliability/0.1"})
    resp.raise_for_status()
    return resp.json()


def fetch_reference_stations(session: requests.Session) -> pd.DataFrame:
    """Active PM2.5 reference stations (id, name, coordinates)."""
    rows = _soql(
        STATIONS_DATASET, session,
        **{"$where": f"nometiposensore='{PM25_TYPE}' AND datastop IS NULL",
           "$select": "idsensore,nomestazione,lat,lng", "$limit": "500"},
    )
    df = pd.DataFrame(rows)
    return df.astype({"idsensore": int, "lat": float, "lng": float})


def fetch_reference_daily(
    sensor_ids: list[int], start: str, end: str, session: requests.Session
) -> pd.DataFrame:
    """Daily PM2.5 per station over the window, dropping ARPA's missing-value flags (< 0)."""
    ids = ",".join(f"'{i}'" for i in sensor_ids)
    rows = _soql(
        MEASUREMENTS_DATASET, session,
        **{"$where": f"idsensore in({ids}) AND data between '{start}T00:00:00' and '{end}T23:59:59'",
           "$select": "idsensore,data,valore", "$limit": "50000"},
    )
    df = pd.DataFrame(rows)
    df["idsensore"] = df["idsensore"].astype(int)
    df["ref_pm25"] = pd.to_numeric(df["valore"], errors="coerce")
    df["date"] = df["data"].str[:10]
    return df.loc[df["ref_pm25"] >= 0, ["idsensore", "date", "ref_pm25"]]


def citizen_daily(curated_dir: str = "data/curated") -> pd.DataFrame:
    """Citizen daily-mean PM2.5 (raw and RH-corrected) and humidity, per location (local day)."""
    df = pd.read_parquet(f"{curated_dir}/hourly").dropna(subset=["pm25_mean"]).copy()
    df["pm25_corrected"] = koehler_correction(df["pm25_mean"], df["humidity_mean"])
    df["date"] = (
        pd.to_datetime(df["window_start"], utc=True).dt.tz_convert(LOCAL_TZ).dt.strftime("%Y-%m-%d")
    )
    return df.groupby(["location_id", "date"], as_index=False).agg(
        cit_pm25=("pm25_mean", "mean"),
        cit_pm25_corrected=("pm25_corrected", "mean"),
        humidity=("humidity_mean", "mean"),
        lat=("latitude", "first"),
        lon=("longitude", "first"),
    )


def assign_nearest(citizen: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Attach each citizen location's nearest reference station id and distance."""
    locs = citizen[["location_id", "lat", "lon"]].drop_duplicates()
    nearest = []
    for loc in locs.itertuples(index=False):
        dists = stations.apply(
            lambda s: haversine_km(loc.lat, loc.lon, s["lat"], s["lng"]), axis=1
        )
        j = dists.idxmin()
        nearest.append((loc.location_id, int(stations.loc[j, "idsensore"]), round(dists[j], 1)))
    return pd.DataFrame(nearest, columns=["location_id", "idsensore", "dist_km"])


def error_percentiles(abs_error: pd.Series) -> dict[str, float]:
    return {q: round(float(abs_error.quantile(p)), 1)
            for q, p in {"p50": 0.5, "p90": 0.9, "p95": 0.95}.items()}


def build_comparison(curated_dir: str, start: str, end: str) -> pd.DataFrame:
    session = requests.Session()
    stations = fetch_reference_stations(session)
    reference = fetch_reference_daily(stations["idsensore"].tolist(), start, end, session)

    citizen = citizen_daily(curated_dir)
    nearest = assign_nearest(citizen, stations)
    citizen = citizen.merge(nearest, on="location_id")

    merged = citizen.merge(reference, on=["idsensore", "date"], how="inner")
    merged["bias"] = merged["cit_pm25"] - merged["ref_pm25"]
    merged["bias_corrected"] = merged["cit_pm25_corrected"] - merged["ref_pm25"]
    return merged


def _plot_scatter(m: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    sc = ax.scatter(m["ref_pm25"], m["cit_pm25"], c=m["dist_km"], cmap="viridis", s=25)
    hi = max(m["ref_pm25"].max(), m["cit_pm25"].max()) * 1.05
    ax.plot([0, hi], [0, hi], "k--", lw=1, label="1:1")
    ax.set_xlabel("ARPA reference PM2.5 (ug/m3, daily)")
    ax.set_ylabel("citizen PM2.5 (ug/m3, daily)")
    ax.set_title("Citizen vs reference PM2.5, Milan")
    ax.legend()
    fig.colorbar(sc, ax=ax, label="distance to station (km)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_error_bars(near: pd.DataFrame, path: Path) -> None:
    raw = error_percentiles(near["bias"].abs())
    cor = error_percentiles(near["bias_corrected"].abs())
    x = list(raw.keys())
    width = 0.35
    idx = range(len(x))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar([i - width / 2 for i in idx], list(raw.values()), width, label="raw")
    ax.bar([i + width / 2 for i in idx], list(cor.values()), width, label="RH-corrected")
    ax.set_xticks(list(idx))
    ax.set_xticklabels(x)
    ax.set_ylabel("absolute error vs reference (ug/m3)")
    ax.set_title(f"Error distribution, near pairs (<= {NEAR_KM:g} km)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare citizen PM2.5 to ARPA reference.")
    parser.add_argument("--start", default="2026-09-01")
    parser.add_argument("--end", default="2026-09-13")
    parser.add_argument("--curated-dir", default="data/curated")
    args = parser.parse_args()

    m = build_comparison(args.curated_dir, args.start, args.end)
    near = m[m["dist_km"] <= NEAR_KM]
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    m.to_csv(artifacts / "reference_pairs.csv", index=False)
    _plot_scatter(m, artifacts / "citizen_vs_reference.png")
    _plot_error_bars(near, artifacts / "error_distribution.png")

    print(f"paired daily rows: {len(m)} ({m['location_id'].nunique()} locations); "
          f"near (<= {NEAR_KM:g} km): {len(near)} ({near['location_id'].nunique()} locations)")
    for label, sub in [("all", m), (f"near <= {NEAR_KM:g} km", near)]:
        print(f"\n[{label}] mean citizen={sub['cit_pm25'].mean():.1f} "
              f"mean reference={sub['ref_pm25'].mean():.1f} ug/m3")
        print(f"  bias (cit-ref): mean={sub['bias'].mean():.1f} median={sub['bias'].median():.1f}")
        print(f"  |error| raw:       {error_percentiles(sub['bias'].abs())}")
        print(f"  |error| corrected: {error_percentiles(sub['bias_corrected'].abs())}")
    print(f"\nwrote artifacts to {artifacts}/")


if __name__ == "__main__":
    main()

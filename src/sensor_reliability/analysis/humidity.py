"""Humidity vs PM analysis over the curated hourly data.

Answers part (a) of the project question as far as the citizen data alone allows: how does
reported PM2.5 vary with relative humidity, and what does a standard RH correction do? The
honest limit is stated up front: without a reference instrument we cannot prove a correction
improves *accuracy* (that is M5). Here we characterise the association, expose its confounders,
and apply the correction, reporting its effect and where it breaks down.

Run:
    python -m sensor_reliability.analysis.humidity
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Minimum valid readings behind an hourly mean for it to be trusted.
MIN_READINGS_PER_HOUR = 3
RH_BINS = [0, 40, 50, 60, 70, 80, 90, 95, 100]
LOCAL_TZ = "Europe/Rome"

# Representative kappa for ambient aerosol; a literature value, not fitted (fitting needs a
# reference). Method: kappa-Koehler hygroscopic growth correction (Crilley et al., 2018, AMT).
DEFAULT_KAPPA = 0.5


def koehler_correction(
    pm_wet: float, rh: float, kappa: float = DEFAULT_KAPPA, rh_cap: float = 99.0
):
    """Dry-PM estimate from a humidity-affected reading, via kappa-Koehler growth.

    pm_dry = pm_wet / (1 + kappa * a_w / (1 - a_w)), with water activity a_w = RH/100.
    The (1 - a_w) term diverges as RH -> 100%, so a_w is capped at rh_cap; that cap is itself a
    statement about where this correction stops being trustworthy. Works on scalars or arrays.
    """
    a_w = np.minimum(rh, rh_cap) / 100.0
    growth = kappa * a_w / (1.0 - a_w)
    return pm_wet / (1.0 + growth)


def load_colocated(curated_dir: str = "data/curated") -> pd.DataFrame:
    """Curated rows that carry both PM2.5 and humidity, with enough readings to be stable."""
    df = pd.read_parquet(f"{curated_dir}/hourly")
    df = df.dropna(subset=["pm25_mean", "humidity_mean"])
    df = df[(df["n_pm25"] >= MIN_READINGS_PER_HOUR) & (df["n_humidity"] >= MIN_READINGS_PER_HOUR)]
    df = df.copy()
    df["local_hour"] = (
        pd.to_datetime(df["window_start"], utc=True).dt.tz_convert(LOCAL_TZ).dt.hour
    )
    df["pm25_corrected"] = koehler_correction(df["pm25_mean"], df["humidity_mean"])
    return df


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman rank correlation without a scipy dependency."""
    return float(a.rank().corr(b.rank()))


def rh_bin_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Median PM2.5 (raw and corrected) and count per humidity bin."""
    binned = pd.cut(df["humidity_mean"], RH_BINS)
    out = df.groupby(binned, observed=True).agg(
        n=("pm25_mean", "size"),
        pm25_raw_median=("pm25_mean", "median"),
        pm25_corrected_median=("pm25_corrected", "median"),
    )
    return out.round(2)


def _plot_pm_vs_rh(summary: pd.DataFrame, path: Path) -> None:
    x = [str(i) for i in summary.index]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(x, summary["pm25_raw_median"], "o-", label="raw")
    ax.plot(x, summary["pm25_corrected_median"], "s--", label="kappa-Koehler corrected")
    ax.set_xlabel("relative humidity bin (%)")
    ax.set_ylabel("median PM2.5 (ug/m3)")
    ax.set_title("PM2.5 vs relative humidity, Milan citizen sensors")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_diurnal(df: pd.DataFrame, path: Path) -> None:
    hourly = df.groupby("local_hour").agg(
        pm25=("pm25_mean", "mean"), rh=("humidity_mean", "mean")
    )
    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax2 = ax1.twinx()
    ax1.plot(hourly.index, hourly["pm25"], "o-", color="tab:red", label="PM2.5")
    ax2.plot(hourly.index, hourly["rh"], "s--", color="tab:blue", label="RH")
    ax1.set_xlabel("hour of day (Europe/Rome)")
    ax1.set_ylabel("mean PM2.5 (ug/m3)", color="tab:red")
    ax2.set_ylabel("mean relative humidity (%)", color="tab:blue")
    ax1.set_title("Diurnal confounding: PM2.5 and humidity by hour of day")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    df = load_colocated()
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)

    summary = rh_bin_summary(df)
    summary.to_csv(artifacts / "rh_bins.csv")
    _plot_pm_vs_rh(summary, artifacts / "pm_vs_rh.png")
    _plot_diurnal(df, artifacts / "diurnal_confound.png")

    print(f"co-located hourly rows: {len(df)} across {df['location_id'].nunique()} locations")
    print(f"Spearman PM2.5 vs RH: {spearman(df['pm25_mean'], df['humidity_mean']):.3f}")
    print("share of rows above RH thresholds (candidate low-confidence flag):")
    for threshold in (85, 90, 95, 99):
        print(f"  RH >= {threshold}%: {(df['humidity_mean'] >= threshold).mean():.3f}")
    print("\nPM2.5 by humidity bin (raw vs corrected median):")
    print(summary.to_string())
    print(f"\nwrote artifacts to {artifacts}/")


if __name__ == "__main__":
    main()

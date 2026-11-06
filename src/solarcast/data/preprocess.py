"""[Member 1] Raw -> processed hourly dataset matching solarcast.schemas.PROCESSED_COLUMNS.

Rules (documented in docs/data_contract.md - agree changes with Member 2):
1. Timestamps: UTC, start of hour, one row per (site_id, hour). Duplicates -> keep last.
2. Units: W/m^2 irradiance, deg C, %, m/s, kWh per hour (converted in the ingesters).
3. Invalid values -> NaN: negative irradiance/generation beyond rounding noise, generation above
   capacity * margin, humidity/cloud outside 0-100, negative wind.
4. Gaps: runs of <= max_gap_hours_interpolate missing hours are linearly interpolated and
   flagged is_imputed=True. Longer gaps are left out (rows dropped), so Member 2's windowing
   must skip windows that cross a missing hour.
5. Night: if GHI < night_ghi_threshold_wm2, generation is set to 0.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from solarcast import schemas as S
from solarcast.config import params

log = logging.getLogger(__name__)

VALID_RANGES = {
    S.GHI: (0, 1400),
    S.GTI: (0, 1500),
    S.TEMP: (-10, 55),
    S.CLOUD_COVER: (0, 100),
    S.REL_HUMIDITY: (0, 100),
    S.WIND_SPEED: (0, 60),
}
NOISE_TOLERANCE = 1e-3  # tiny negatives from upstream rounding are clipped to 0, not nulled


def interpolate_short_gaps(s: pd.Series, max_gap: int) -> tuple[pd.Series, pd.Series]:
    """Linearly fill NaN runs of length <= max_gap that have data on both sides.

    Returns (filled series, boolean mask of filled positions). Longer runs stay NaN.
    """
    isna = s.isna()
    run_id = (isna != isna.shift()).cumsum()
    run_len = isna.groupby(run_id).transform("sum")
    candidate = isna & (run_len <= max_gap)
    interp = s.interpolate(method="linear", limit_area="inside")
    filled = s.where(~candidate, interp)
    mask = candidate & filled.notna()
    return filled, mask


def _regularise(df: pd.DataFrame) -> pd.DataFrame:
    """Sort, drop duplicate hours (keep last) and reindex onto a complete hourly grid."""
    df = df.copy()
    df[S.TIMESTAMP] = pd.to_datetime(df[S.TIMESTAMP], utc=True).dt.floor("h")
    n_dupes = int(df.duplicated(S.TIMESTAMP).sum())
    if n_dupes:
        log.warning("dropping %d duplicate timestamps (keep last)", n_dupes)
    df = df.drop_duplicates(S.TIMESTAMP, keep="last").set_index(S.TIMESTAMP).sort_index()
    grid = pd.date_range(df.index.min(), df.index.max(), freq="h", tz="UTC", name=S.TIMESTAMP)
    return df.reindex(grid)


def clean_weather(df: pd.DataFrame) -> pd.DataFrame:
    max_gap = params()["data"]["max_gap_hours_interpolate"]
    df = _regularise(df[[S.TIMESTAMP, *S.WEATHER_COLUMNS]])
    imputed = pd.Series(False, index=df.index)
    for col, (lo, hi) in VALID_RANGES.items():
        v = df[col].astype(float)
        v = v.mask(v.between(lo - NOISE_TOLERANCE, lo), lo)  # rounding noise just below 0
        v = v.where(v.between(lo, hi))
        df[col], mask = interpolate_short_gaps(v, max_gap)
        imputed |= mask
    df[S.IS_IMPUTED] = imputed
    return df.reset_index()


def clean_generation(df: pd.DataFrame, capacity_kw: float) -> pd.DataFrame:
    p = params()["data"]
    keep = [S.TIMESTAMP, S.GENERATION_KWH, S.SOURCE, S.IS_SIMULATED]
    df = _regularise(df[keep])
    g = df[S.GENERATION_KWH].astype(float)
    g = g.mask(g.between(-NOISE_TOLERANCE, 0), 0.0)
    g = g.where(g.between(0, capacity_kw * p["generation_capacity_margin"]))
    df[S.GENERATION_KWH], mask = interpolate_short_gaps(g, p["max_gap_hours_interpolate"])
    df[[S.SOURCE, S.IS_SIMULATED]] = df[[S.SOURCE, S.IS_SIMULATED]].ffill().bfill()
    df["gen_imputed"] = mask
    return df.reset_index()


def align_weather_and_generation(
    weather: pd.DataFrame, generation: pd.DataFrame, site: dict
) -> pd.DataFrame:
    """Join cleaned weather + generation for one site, apply the night rule, drop long gaps."""
    threshold = params()["data"]["night_ghi_threshold_wm2"]
    df = weather.merge(generation, on=S.TIMESTAMP, how="inner")
    df[S.IS_IMPUTED] = df[S.IS_IMPUTED] | df.pop("gen_imputed")
    night = df[S.GHI] < threshold
    df.loc[night, S.GENERATION_KWH] = 0.0
    df[S.SITE_ID] = site["site_id"]
    df[S.PANEL_CAPACITY_KW] = float(site["panel_capacity_kw"])

    before = len(df)
    df = df.dropna(subset=[S.GENERATION_KWH, *S.WEATHER_COLUMNS])
    if len(df) < before:
        log.warning("%s: dropped %d rows in gaps longer than the interpolation limit",
                    site["site_id"], before - len(df))

    df[S.IS_SIMULATED] = df[S.IS_SIMULATED].astype(bool)
    df[S.IS_IMPUTED] = df[S.IS_IMPUTED].astype(bool)
    return df[S.PROCESSED_COLUMNS].reset_index(drop=True)


def build_site_dataset(weather_raw: pd.DataFrame, generation_raw: pd.DataFrame,
                       site: dict) -> pd.DataFrame:
    weather = clean_weather(weather_raw)
    generation = clean_generation(generation_raw, site["panel_capacity_kw"])
    return align_weather_and_generation(weather, generation, site)


def summarise(df: pd.DataFrame) -> dict:
    """Small JSON-able summary logged with every processed dataset."""
    per_site = {}
    for site_id, g in df.groupby(S.SITE_ID):
        per_site[site_id] = {
            "rows": len(g),
            "start": g[S.TIMESTAMP].min().isoformat(),
            "end": g[S.TIMESTAMP].max().isoformat(),
            "imputed_rows": int(g[S.IS_IMPUTED].sum()),
            "total_kwh": round(float(g[S.GENERATION_KWH].sum()), 1),
            "sources": sorted(g[S.SOURCE].unique().tolist()),
        }
    return {"rows": len(df), "sites": per_site,
            "null_cells": int(np.asarray(df.isna()).sum())}

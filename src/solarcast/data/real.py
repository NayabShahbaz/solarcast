"""[Member 1] Real site: clean inverter exports into hourly + daily data with quality flags.

    python -m solarcast.data.real          # every real site in configs/sites.yaml

Run by the site owner only: the raw exports (data/inverter/<folder>/) never leave their machine.
Output goes to data/real/<site_id>/ without identifiers, and is versioned with
`dvc add data/real` + `dvc push`, so teammates `dvc pull` it and their `dvc repro` is unaffected.

The real site is used to TEST the model on a real roof. Training stays on PVGIS (simulated).

Cleaning rules (thresholds in params.yaml -> real_site; evidence in docs/data_contract.md):
1. Days before the install date are dropped.
2. Night -> 0 kWh. A 5-minute reading counts as daylight only if the sun is above the horizon
   AND the PV voltage is at least `night_pv_voltage_v`: after the 2025 expansion the longer
   panel string shows up to ~90 V and ~0.08 kW at night (stray light), so voltage alone isn't
   enough. Export hours with the sun below the horizon for the whole hour are set to 0.
3. Hourly kWh comes from the 5-minute readings where an hour has at least
   `min_readings_per_hour` of them; otherwise from the export's hourly columns, rescaled so
   the day's daylight hours add up to the reported daily total (those columns read ~9 % low).
4. A day is an OUTAGE when it produced less than `outage_fraction` of what its sunshine would
   normally give (sunshine x the median kWh-per-sunshine of the surrounding
   `outage_window_days` days). Outage days stay in the data, flagged.
5. An hour is HELD BACK when, in at least `held_back_min_share` of its daylight 5-minute
   readings, the battery is >= `held_back_battery_pct` and charging <= `held_back_charge_a`
   (no grid feed-in, so the inverter limits solar). Unknown (NA) without 5-minute data.
6. `usable` = complete day, not an outage, not held back. Only usable hours count toward
   accuracy; the rest are reported separately.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from solarcast import schemas as S
from solarcast.config import INVERTER_DIR, REAL_DIR, ROOT, params, sites
from solarcast.data.ingest import inverter as inv
from solarcast.data.ingest import open_meteo

try:  # pandera >= 0.24 moved the pandas API here
    import pandera.pandas as pa
except ImportError:  # pragma: no cover
    import pandera as pa

log = logging.getLogger("solarcast.real")

# extra columns of the real-site files (on top of the shared schema names)
HOURLY_FROM = "hourly_from"     # "5min" | "hourly_export"
IS_SCALED = "is_scaled"         # export hour rescaled to the daily total
IS_PARTIAL = "is_partial"       # the day is incomplete (install day, today, missing hours)
IS_OUTAGE = "is_outage"         # nullable: NA when there's no weather yet to judge
HELD_BACK = "held_back"         # nullable: NA without 5-minute battery data
USABLE = "usable"
SUN_KWH_M2 = "sun_kwh_m2"       # daily sunshine on flat ground at the site (Open-Meteo)
EXPECTED_KWH = "expected_kwh"
DAILY_SOURCE = "report"


def real_sites() -> list[dict]:
    return [s for s in sites() if not s.get("is_simulated", True)]


# --------------------------------------------------------------------------- helpers
def sun_elevation_deg(ts_utc: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    """Approximate solar elevation (NOAA low-precision formulas, error well under 1 degree)."""
    doy = ts_utc.dayofyear.to_numpy()
    b = np.radians(360 / 365 * (doy - 81))
    decl = np.radians(23.44) * np.sin(b)
    eot_min = 9.87 * np.sin(2 * b) - 7.53 * np.cos(b) - 1.5 * np.sin(b)
    minutes = ts_utc.hour.to_numpy() * 60 + ts_utc.minute.to_numpy()
    hour_angle = np.radians((minutes + 4 * lon + eot_min) / 4 - 180)
    phi = np.radians(lat)
    return np.degrees(np.arcsin(np.sin(phi) * np.sin(decl)
                                + np.cos(phi) * np.cos(decl) * np.cos(hour_angle)))


def night_hours(ts: pd.Series, lat: float, lon: float) -> np.ndarray:
    """True where the sun is below the horizon for the whole hour starting at ts (UTC)."""
    idx = pd.DatetimeIndex(ts)
    elev = [sun_elevation_deg(idx + pd.Timedelta(minutes=m), lat, lon) for m in (0, 30, 60)]
    return np.all(np.vstack(elev) <= 0, axis=0)


def portal_day(ts: pd.Series, hour_tz: str) -> pd.Series:
    """Calendar day in the portal's timezone (the day the exports file an hour under)."""
    return pd.DatetimeIndex(ts).tz_convert(hour_tz).tz_localize(None).normalize().to_series(
        index=ts.index)


def capacity_on(dates: pd.Series, history: list[dict] | None) -> pd.Series:
    """Panel kW in force on each date, from the site's capacity_history (NaN if unknown)."""
    out = pd.Series(np.nan, index=dates.index)
    for step in sorted(history or [], key=lambda s: str(s["from"])):
        out[dates >= pd.Timestamp(str(step["from"]))] = float(step["panel_capacity_kw"])
    return out


# --------------------------------------------------------------------------- hourly
def hourly_from_snapshots(snaps: pd.DataFrame, site: dict, cfg: dict) -> pd.DataFrame:
    """Mean PV power per clock hour (kW x 1 h = kWh) + the held-back flag for that hour."""
    if snaps.empty:
        return pd.DataFrame()
    s = snaps.set_index(S.TIMESTAMP).sort_index()
    sun_up = sun_elevation_deg(s.index, site["latitude"], site["longitude"]) > 0
    daylight = (s[inv.PV_V] >= cfg["night_pv_voltage_v"]) & sun_up
    pv = s[inv.PV_KW].clip(lower=0).where(daylight, 0.0)
    g = pv.resample("1h")
    out = pd.DataFrame({S.GENERATION_KWH: g.mean(), "n": g.count()})
    out = out[out["n"] >= cfg["min_readings_per_hour"]]

    if {inv.BATTERY_PCT, inv.CHARGE_A} <= set(s.columns):
        full = (s[inv.BATTERY_PCT] >= cfg["held_back_battery_pct"]) & (
            s[inv.CHARGE_A] <= cfg["held_back_charge_a"])
        share = full[daylight].resample("1h").mean()
        held = (share >= cfg["held_back_min_share"]).astype("boolean")
        out[HELD_BACK] = held.reindex(out.index).fillna(False)   # no daylight -> nothing held back
    else:
        out[HELD_BACK] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out[HOURLY_FROM] = "5min"
    out[IS_SCALED] = False
    return out.drop(columns="n").rename_axis(S.TIMESTAMP).reset_index()


def hourly_from_export(hourly: pd.DataFrame, daily: pd.DataFrame, site: dict,
                       cfg: dict) -> tuple[pd.DataFrame, pd.Series]:
    """Export hourly columns: night -> 0, daylight rescaled to the daily total (complete days)."""
    if hourly.empty:
        return pd.DataFrame(), pd.Series(dtype=float)
    h = hourly.copy()
    h["night"] = night_hours(h[S.TIMESTAMP], site["latitude"], site["longitude"])
    n = h.groupby(inv.DATE)[inv.HOURLY_RAW_KWH].transform("size")
    h["complete"] = n == 24
    day_raw = h[~h.night].groupby(inv.DATE)[inv.HOURLY_RAW_KWH].sum()
    night_raw = h[h.night].groupby(inv.DATE)[inv.HOURLY_RAW_KWH].sum()
    totals = daily.set_index(inv.DATE)[inv.DAILY_KWH]
    target = totals.reindex(day_raw.index) - night_raw.reindex(day_raw.index).fillna(0)
    scale = (target / day_raw).where(day_raw > 0)
    complete_days = h.loc[h.complete, inv.DATE].unique()
    scale = scale[scale.index.isin(complete_days)]

    factor = h[inv.DATE].map(scale)
    scaled = h.complete & factor.notna()
    kwh = h[inv.HOURLY_RAW_KWH].where(~scaled, h[inv.HOURLY_RAW_KWH] * factor)
    h[S.GENERATION_KWH] = kwh.where(~h.night, 0.0).clip(lower=0)
    h[IS_SCALED] = scaled & ~h.night
    h[HOURLY_FROM] = "hourly_export"
    h[HELD_BACK] = pd.Series(pd.NA, index=h.index, dtype="boolean")
    h.loc[h.night, HELD_BACK] = False
    cols = [S.TIMESTAMP, S.GENERATION_KWH, HELD_BACK, HOURLY_FROM, IS_SCALED]
    return h[cols], scale


# --------------------------------------------------------------------------- daily flags
def flag_outages(daily: pd.DataFrame, sun: pd.Series, cfg: dict) -> pd.DataFrame:
    """Adds sun_kwh_m2, expected_kwh, is_outage (NA where sunshine is unknown or day partial)."""
    d = daily.copy()
    d[SUN_KWH_M2] = d[inv.DATE].map(sun)
    ratio = (d[inv.DAILY_KWH] / d[SUN_KWH_M2]).where(~d[IS_PARTIAL] & (d[SUN_KWH_M2] > 0))
    typical = ratio.rolling(cfg["outage_window_days"], center=True, min_periods=5).median()
    d[EXPECTED_KWH] = (d[SUN_KWH_M2] * typical).round(3)
    judged = d[EXPECTED_KWH].notna() & ~d[IS_PARTIAL]
    out = pd.Series(pd.NA, index=d.index, dtype="boolean")
    out[judged] = d.loc[judged, inv.DAILY_KWH] < cfg["outage_fraction"] * d.loc[judged, EXPECTED_KWH]
    d[IS_OUTAGE] = out
    return d


def daily_sunshine(site: dict, start: pd.Timestamp, end: pd.Timestamp, hour_tz: str) -> pd.Series:
    """kWh/m^2 of sunshine per portal day; days without all 24 hours are left out."""
    ghi = open_meteo.fetch_ghi_history(site["latitude"], site["longitude"],
                                       (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                                       min(end + pd.Timedelta(days=1), pd.Timestamp.now(tz="UTC")
                                           .tz_localize(None)).strftime("%Y-%m-%d")).dropna()
    days = portal_day(ghi.index.to_series(), hour_tz)
    g = ghi.groupby(days.to_numpy())
    return (g.sum() / 1000).where(g.count() == 24).dropna()


# --------------------------------------------------------------------------- build
def build_site(site: dict, sun: pd.Series | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """-> (hourly, daily, summary) for one real site. `sun` can be passed in tests."""
    cfg = params()["real_site"]
    tz = site["export_hour_timezone"]
    folder = INVERTER_DIR / site["export_folder"]
    ex = inv.read_folder(folder, tz)
    installed = pd.Timestamp(str(site["installed"]))

    daily = ex["daily"][ex["daily"][inv.DATE] >= installed].reset_index(drop=True)
    hourly_5 = hourly_from_snapshots(ex["snapshots"], site, cfg)
    hourly_x, scale = hourly_from_export(
        ex["hourly"][ex["hourly"][inv.DATE] >= installed] if len(ex["hourly"]) else ex["hourly"],
        daily, site, cfg)
    hourly = (pd.concat([hourly_5, hourly_x], ignore_index=True)
              .drop_duplicates(S.TIMESTAMP, keep="first")         # 5-minute data wins
              .sort_values(S.TIMESTAMP).reset_index(drop=True))
    hourly[HELD_BACK] = hourly[HELD_BACK].astype("boolean")
    hourly["_day"] = portal_day(hourly[S.TIMESTAMP], tz).to_numpy()
    hourly = hourly[hourly["_day"] >= installed]

    # completeness per portal day (hourly), and partial days at the daily level
    n_hours = hourly.groupby("_day").size()
    hourly[IS_PARTIAL] = hourly["_day"].map(n_hours) < 24
    partial_days = set(n_hours[n_hours < 24].index) | {installed}
    daily[IS_PARTIAL] = daily[inv.DATE].isin(partial_days)
    daily["has_hourly"] = daily[inv.DATE].isin(set(n_hours.index))

    if sun is None:
        sun = daily_sunshine(site, daily[inv.DATE].min(), daily[inv.DATE].max(), tz)
    daily = flag_outages(daily, sun, cfg)
    hourly[IS_OUTAGE] = hourly["_day"].map(daily.set_index(inv.DATE)[IS_OUTAGE]).astype("boolean")
    hourly[USABLE] = (~hourly[IS_PARTIAL] & hourly[IS_OUTAGE].eq(False).fillna(False)
                      & ~hourly[HELD_BACK].fillna(False).astype(bool)).astype(bool)

    history = site.get("capacity_history")
    hourly[S.PANEL_CAPACITY_KW] = capacity_on(hourly["_day"], history)
    daily[S.PANEL_CAPACITY_KW] = capacity_on(daily[inv.DATE], history)
    hourly[S.SITE_ID] = daily[S.SITE_ID] = site["site_id"]
    hourly[S.SOURCE] = "inverter"
    hourly[S.IS_SIMULATED] = False
    hourly = hourly.drop(columns="_day")[[
        S.TIMESTAMP, S.SITE_ID, S.SOURCE, S.IS_SIMULATED, S.GENERATION_KWH, S.PANEL_CAPACITY_KW,
        HOURLY_FROM, IS_SCALED, IS_PARTIAL, IS_OUTAGE, HELD_BACK, USABLE]].reset_index(drop=True)
    daily = daily.rename(columns={inv.DAILY_KWH: S.GENERATION_KWH})[[
        inv.DATE, S.SITE_ID, S.GENERATION_KWH, S.PANEL_CAPACITY_KW, DAILY_SOURCE, "has_hourly",
        SUN_KWH_M2, EXPECTED_KWH, IS_PARTIAL, IS_OUTAGE]]

    summary = summarise(hourly, daily, scale, ex, site, cfg)
    return validate_hourly(hourly, site), validate_daily(daily), summary


def summarise(hourly: pd.DataFrame, daily: pd.DataFrame, scale: pd.Series, ex: dict,
              site: dict, cfg: dict) -> dict:
    lo, hi = cfg["scale_warn_range"]
    odd = scale[(scale < lo) | (scale > hi)]
    if len(odd):
        log.warning("%d days have an unusual hourly->daily scale factor: %s", len(odd),
                    {str(k.date()): round(float(v), 2) for k, v in odd.items()})
    missing = [k for k in ("capacity_history", "tilt_deg") if site.get(k) is None]
    if missing:
        log.warning("%s: not set yet in configs/sites.yaml: %s", site["site_id"], missing)
    day_rng = lambda df, c: [str(df[c].min())[:10], str(df[c].max())[:10]]
    return {
        "site_id": site["site_id"],
        "export_files": ex["files"],
        "daily": {
            "days": len(daily), "range": day_rng(daily, inv.DATE),
            "with_hourly": int(daily["has_hourly"].sum()),
            "partial_days": sorted(str(d)[:10] for d in daily.loc[daily[IS_PARTIAL], inv.DATE]),
            "outage_days": sorted(str(d)[:10] for d in daily.loc[daily[IS_OUTAGE].eq(True).fillna(False), inv.DATE]),
            "not_judged_no_weather": int(daily[IS_OUTAGE].isna().sum() - daily[IS_PARTIAL].sum()),
            "conflicting_totals": ex["conflicts"],
        },
        "hourly": {
            "hours": len(hourly), "range": day_rng(hourly, S.TIMESTAMP),
            "from_5min": int((hourly[HOURLY_FROM] == "5min").sum()),
            "from_export_rescaled": int(hourly[IS_SCALED].sum()),
            "scale_factor": {"median": round(float(scale.median()), 3) if len(scale) else None,
                             "min": round(float(scale.min()), 3) if len(scale) else None,
                             "max": round(float(scale.max()), 3) if len(scale) else None,
                             "unusual_days": len(odd)},
            "held_back_hours": int(hourly[HELD_BACK].eq(True).fillna(False).sum()),
            "held_back_unknown_hours": int(hourly[HELD_BACK].isna().sum()),
            "usable_hours": int(hourly[USABLE].sum()),
        },
        "not_set_yet": missing,
    }


# --------------------------------------------------------------------------- validation
def _utc_hourly(ts: pd.Series) -> bool:
    return bool(str(ts.dt.tz) == "UTC" and (ts.dt.minute == 0).all() and (ts.dt.second == 0).all())


def validate_hourly(df: pd.DataFrame, site: dict) -> pd.DataFrame:
    margin = params()["data"]["generation_capacity_margin"]
    checks = [pa.Check(  # skipped while the capacity is unknown (NaN)
        lambda d: d[S.PANEL_CAPACITY_KW].isna()
        | (d[S.GENERATION_KWH] <= d[S.PANEL_CAPACITY_KW] * margin + 1e-9),
        error="generation_kwh exceeds panel capacity * margin")]
    schema = pa.DataFrameSchema(
        {
            S.TIMESTAMP: pa.Column(pd.DatetimeTZDtype("ns", "UTC"), unique=True, checks=pa.Check(
                _utc_hourly, element_wise=False, error="timestamp must be UTC start-of-hour")),
            S.SITE_ID: pa.Column(str, pa.Check.eq(site["site_id"])),
            S.SOURCE: pa.Column(str, pa.Check.eq("inverter")),
            S.IS_SIMULATED: pa.Column(bool, pa.Check.eq(False)),
            S.GENERATION_KWH: pa.Column(float, pa.Check.ge(0), nullable=False),
            S.PANEL_CAPACITY_KW: pa.Column(float, pa.Check.gt(0), nullable=True),
            HOURLY_FROM: pa.Column(str, pa.Check.isin(["5min", "hourly_export"])),
            IS_SCALED: pa.Column(bool),
            IS_PARTIAL: pa.Column(bool),
            IS_OUTAGE: pa.Column("boolean", nullable=True),
            HELD_BACK: pa.Column("boolean", nullable=True),
            USABLE: pa.Column(bool),
        },
        checks=checks, strict=True, name="real_hourly",
    )
    return schema.validate(df, lazy=True)


def validate_daily(df: pd.DataFrame) -> pd.DataFrame:
    schema = pa.DataFrameSchema(
        {
            inv.DATE: pa.Column("datetime64[ns]", unique=True),
            S.SITE_ID: pa.Column(str),
            S.GENERATION_KWH: pa.Column(float, pa.Check.ge(0)),
            S.PANEL_CAPACITY_KW: pa.Column(float, pa.Check.gt(0), nullable=True),
            DAILY_SOURCE: pa.Column(str, pa.Check.isin(["device_monthly", "owner_monthly"])),
            "has_hourly": pa.Column(bool),
            SUN_KWH_M2: pa.Column(float, pa.Check.ge(0), nullable=True),
            EXPECTED_KWH: pa.Column(float, pa.Check.ge(0), nullable=True),
            IS_PARTIAL: pa.Column(bool),
            IS_OUTAGE: pa.Column("boolean", nullable=True),
        },
        strict=True, name="real_daily",
    )
    return schema.validate(df, lazy=True)


# --------------------------------------------------------------------------- save / CLI
def save(site_id: str, hourly: pd.DataFrame, daily: pd.DataFrame, summary: dict) -> Path:
    out = REAL_DIR / site_id
    out.mkdir(parents=True, exist_ok=True)
    hourly.to_parquet(out / "hourly.parquet", index=False)
    daily.to_parquet(out / "daily.parquet", index=False)
    # LF + no timestamps: same data -> same DVC hash
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8",
                                      newline="\n")
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m solarcast.data.real", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", help="one site_id (default: every real site)")
    a = ap.parse_args(argv)
    chosen = [s for s in real_sites() if a.site in (None, s["site_id"])]
    if not chosen:
        log.error("no real site%s in configs/sites.yaml", f" '{a.site}'" if a.site else "s")
        return 1
    for site in chosen:
        try:
            hourly, daily, summary = build_site(site)
        except pa.errors.SchemaErrors as e:
            log.error("%s: validation FAILED:\n%s", site["site_id"], e.failure_cases.head(20))
            return 1
        out = save(site["site_id"], hourly, daily, summary)
        log.info("%s -> %s\n%s", site["site_id"], out.relative_to(ROOT),
                 json.dumps(summary, indent=2))
    log.info("next: dvc add data/real && dvc push && git add data/real.dvc data/.gitignore")
    return 0


if __name__ == "__main__":
    sys.exit(main())

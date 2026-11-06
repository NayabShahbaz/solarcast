"""[Member 1] Evidently data drift on model INPUTS (weather features), per site.

Reference = training data from the SAME season (day-of-year within +/- window of the current
dates, all training years). Comparing two weeks of November with a whole year would flag drift
every day from seasonality alone.
Current   = the most recent `monitoring.current_window_days` of ingested inputs
            (data/interim/recent). If daily ingestion hasn't run yet, the last window of the
            processed test split is used instead, and labelled as such.
Only daylight hours are compared: identical zero-irradiance nights would dilute real drift.

simulate_drift=True applies a controlled smog-like shift (less irradiance, more cloud and
humidity) to the current window, to demonstrate the drift -> retraining path.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd

from solarcast import schemas as S
from solarcast.config import REPORTS_DIR, params
from solarcast.data import storage
from solarcast.data.pipeline import PROCESSED_FILE, RECENT_DIR, simulated_sites

log = logging.getLogger(__name__)

MONITORING_DIR = REPORTS_DIR / "monitoring"
DRIFT_COLUMNS = list(S.WEATHER_COLUMNS)


def _daylight(df: pd.DataFrame) -> pd.DataFrame:
    return df[df[S.GHI] >= params()["data"]["night_ghi_threshold_wm2"]]


def seasonal_reference(processed: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    train_end = pd.Timestamp(params()["split"]["train_end"], tz="UTC") + pd.Timedelta(days=1)
    train = processed[processed[S.TIMESTAMP] < train_end]
    pad = params()["monitoring"]["current_window_days"]
    doy_cur = current[S.TIMESTAMP].dt.dayofyear
    lo, hi = doy_cur.min() - pad, doy_cur.max() + pad
    doy = train[S.TIMESTAMP].dt.dayofyear
    if lo < 1 or hi > 366:  # window wraps around new year
        mask = (doy >= (lo % 366 or 366)) | (doy <= (hi % 366))
    else:
        mask = doy.between(lo, hi)
    return train[mask]


def current_window(site_id: str, processed: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    days = params()["monitoring"]["current_window_days"]
    recent_path = RECENT_DIR / f"{site_id}.parquet"
    if recent_path.exists():
        df, label = pd.read_parquet(recent_path), "recent_ingestion"
    else:
        df, label = processed[processed[S.SITE_ID] == site_id], "processed_test_split_fallback"
    end = df[S.TIMESTAMP].max()
    return df[df[S.TIMESTAMP] > end - pd.Timedelta(days=days)], label


def apply_demo_drift(df: pd.DataFrame) -> pd.DataFrame:
    """Controlled winter-smog-like shift: -40% irradiance, +30 pp cloud, +20 pp humidity."""
    out = df.copy()
    out[S.GHI] *= 0.6
    out[S.GTI] *= 0.6
    out[S.CLOUD_COVER] = (out[S.CLOUD_COVER] + 30).clip(upper=100)
    out[S.REL_HUMIDITY] = (out[S.REL_HUMIDITY] + 20).clip(upper=100)
    return out


def run_drift_report(reference: pd.DataFrame, current: pd.DataFrame, name: str) -> dict:
    """Run Evidently, save HTML + JSON to reports/monitoring/, return a stable summary dict."""
    from solarcast.monitoring import _evidently

    MONITORING_DIR.mkdir(parents=True, exist_ok=True)
    html = MONITORING_DIR / f"drift_{name}.html"
    result = _evidently.data_drift(reference[DRIFT_COLUMNS], current[DRIFT_COLUMNS], html)
    storage.maybe_upload(html, storage.key("monitoring", html.name))
    return result | {"report_html": str(html.relative_to(REPORTS_DIR.parent))}


def run_for_all_sites(simulate_drift: bool = False) -> dict:
    if not PROCESSED_FILE.exists():
        raise FileNotFoundError(f"{PROCESSED_FILE} missing - run ingestion (history) or dvc pull")
    processed = pd.read_parquet(PROCESSED_FILE)
    out = {"run_at": datetime.now(UTC).isoformat(timespec="seconds"), "sites": {}}
    for site in simulated_sites():
        sid = site["site_id"]
        current, label = current_window(sid, processed)
        if simulate_drift:
            current = apply_demo_drift(current)
        current = _daylight(current)
        reference = _daylight(seasonal_reference(processed[processed[S.SITE_ID] == sid], current))
        summary = run_drift_report(reference, current, f"{sid}_demo" if simulate_drift else sid)
        out["sites"][sid] = summary | {
            "reference_rows": len(reference),
            "current_rows": len(current),
            "current_from": current[S.TIMESTAMP].min().isoformat(),
            "current_to": current[S.TIMESTAMP].max().isoformat(),
            "current_source": label,
            "simulated_drift": simulate_drift,
        }
        log.info("%s drift: share=%.2f drifted=%s", sid, summary["drift_share"],
                 summary["drifted_columns"])
    return out

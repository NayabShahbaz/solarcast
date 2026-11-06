"""[Member 1] Predicted-vs-actual errors, the retrain decision, and the monitoring summary JSON.

Forecast log contract (written by the daily prediction step / API - Member 3):
  data/interim/forecasts/<site_id>_<YYYY-MM-DD>.parquet
  columns: timestamp (UTC start of hour), p10_kwh, p50_kwh, p90_kwh, model_version
Actuals come from data/interim/recent/<site_id>.parquet (written by daily ingestion).

Dashboard contract (Member 3 reads this - keep keys stable):
  reports/monitoring/latest.json    latest drift + errors + decision
  reports/monitoring/history.jsonl  one line per monitoring run
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from solarcast import schemas as S
from solarcast.config import INTERIM_DIR, REPORTS_DIR, params
from solarcast.data import storage
from solarcast.data.pipeline import RECENT_DIR, simulated_sites

log = logging.getLogger(__name__)

FORECAST_LOG_DIR = INTERIM_DIR / "forecasts"
MONITORING_DIR = REPORTS_DIR / "monitoring"


def compute_forecast_errors(forecasts: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Hourly errors for hours present in both. Daylight-only metrics avoid flattering MAE."""
    m = forecasts.merge(actuals[[S.TIMESTAMP, S.GENERATION_KWH, S.GHI]], on=S.TIMESTAMP)
    m["error_kwh"] = m["p50_kwh"] - m[S.GENERATION_KWH]
    m["in_interval"] = m[S.GENERATION_KWH].between(m["p10_kwh"], m["p90_kwh"])
    m["daylight"] = m[S.GHI] >= params()["data"]["night_ghi_threshold_wm2"]
    return m


def summarise_errors(err: pd.DataFrame) -> dict:
    day = err[err["daylight"]]
    if day.empty:
        return {"hours": 0}
    return {
        "hours": len(day),
        "mae_kwh": round(float(day["error_kwh"].abs().mean()), 4),
        "rmse_kwh": round(float(np.sqrt((day["error_kwh"] ** 2).mean())), 4),
        "bias_kwh": round(float(day["error_kwh"].mean()), 4),
        "interval_coverage": round(float(day["in_interval"].mean()), 3),
        "from": day[S.TIMESTAMP].min().isoformat(),
        "to": day[S.TIMESTAMP].max().isoformat(),
    }


def run_for_all_sites() -> dict | None:
    """Errors per site over all logged forecasts that now have actuals. None if nothing to score."""
    out = {}
    for site in simulated_sites():
        sid = site["site_id"]
        files = sorted(FORECAST_LOG_DIR.glob(f"{sid}_*.parquet"))
        recent = RECENT_DIR / f"{sid}.parquet"
        if not files or not recent.exists():
            continue
        forecasts = pd.concat([pd.read_parquet(f) for f in files]).drop_duplicates(
            S.TIMESTAMP, keep="last"
        )
        summary = summarise_errors(compute_forecast_errors(forecasts, pd.read_parquet(recent)))
        if summary["hours"]:
            out[sid] = summary
    if not out:
        log.info("no forecasts with matching actuals yet - skipping error monitoring")
    return out or None


def load_history() -> list[dict]:
    path = MONITORING_DIR / "history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _drift_streak(site_id: str, current_share: float, history: list[dict], thr: float) -> int:
    """Consecutive runs (latest first, one per day, including this one) with share > thr."""
    if current_share <= thr:
        return 0
    streak, seen_days = 1, {datetime.now(UTC).date().isoformat()}
    for rec in reversed(history):
        site = ((rec.get("drift") or {}).get("sites") or {}).get(site_id)
        if not site or site.get("simulated_drift"):
            continue
        day = rec["run_at"][:10]
        if day in seen_days:  # several runs on one day count once
            continue
        if site.get("drift_share", 0) <= thr:
            break
        seen_days.add(day)
        streak += 1
    return streak


def _days_since_training(history: list[dict]) -> float | None:
    for rec in reversed(history):
        if (rec.get("training") or {}).get("status") == "trained":
            then = datetime.fromisoformat(rec["run_at"])
            return (datetime.now(UTC) - then).total_seconds() / 86400
    return None


def should_retrain(drift_summary: dict, error_summary: dict | None = None,
                   force: bool = False, history: list[dict] | None = None) -> dict:
    """Retraining TRIGGER only. Whether the new model is deployed is decided by evaluation.

    Drift must persist for `drift_consecutive_runs` daily runs (one unusual week of weather is
    not a reason to retrain), except in the controlled demo. No retrain within
    `retrain_cooldown_days` of the last one unless forced.
    """
    cfg = params()["monitoring"]
    history = history or []
    thr, need = cfg["drift_share_threshold"], cfg["drift_consecutive_runs"]
    reasons, notes = [], []
    if force:
        reasons.append("forced")
    for sid, d in (drift_summary or {}).get("sites", {}).items():
        share = d.get("drift_share", 0)
        if share <= thr:
            continue
        if d.get("simulated_drift"):
            reasons.append(f"{sid}: controlled demo drift, share {share:.2f} > {thr}")
            continue
        streak = _drift_streak(sid, share, history, thr)
        if streak >= need:
            reasons.append(f"{sid}: drift share > {thr} for {streak} consecutive daily runs")
        else:
            notes.append(f"{sid}: drift share {share:.2f} > {thr}, streak {streak}/{need}")
    threshold = cfg.get("mae_threshold_kwh")
    for sid, e in (error_summary or {}).items():
        if threshold is not None and e.get("mae_kwh", 0) > threshold:
            reasons.append(f"{sid}: MAE {e['mae_kwh']:.3f} kWh > {threshold}")

    since = _days_since_training(history)
    if reasons and not force and since is not None and since < cfg["retrain_cooldown_days"]:
        notes.append(f"suppressed by cooldown: last training {since:.1f} days ago")
        return {"retrain": False, "reasons": reasons, "notes": notes}
    return {"retrain": bool(reasons), "reasons": reasons, "notes": notes}


def write_monitoring_summary(drift_summary: dict, error_summary: dict | None,
                             decision: dict, training: dict | None = None) -> dict:
    MONITORING_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "drift": drift_summary,
        "errors": error_summary,
        "decision": decision,
        "training": training or {"status": "not_triggered"},
    }
    latest = MONITORING_DIR / "latest.json"
    latest.write_text(json.dumps(record, indent=2), encoding="utf-8")
    with open(MONITORING_DIR / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    storage.maybe_upload(latest, storage.key("monitoring", "latest.json"))
    storage.maybe_upload(MONITORING_DIR / "history.jsonl",
                         storage.key("monitoring", "history.jsonl"))
    return record

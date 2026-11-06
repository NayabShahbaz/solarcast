from datetime import UTC, datetime, timedelta

import pandas as pd

from solarcast import schemas as S
from solarcast.monitoring import errors


def test_error_metrics_daylight_only():
    ts = pd.date_range("2023-01-01", periods=4, freq="h", tz="UTC")
    fc = pd.DataFrame({S.TIMESTAMP: ts, "p10_kwh": [0, 1, 2, 0], "p50_kwh": [0, 2, 4, 0],
                       "p90_kwh": [0, 3, 6, 0]})
    act = pd.DataFrame({S.TIMESTAMP: ts, S.GENERATION_KWH: [0, 3, 3, 0],
                        S.GHI: [0, 300, 500, 0]})
    s = errors.summarise_errors(errors.compute_forecast_errors(fc, act))
    assert s["hours"] == 2
    assert s["mae_kwh"] == 1.0
    assert s["interval_coverage"] == 1.0


def _drift(share, simulated=False):
    return {"sites": {"a": {"drift_share": share, "simulated_drift": simulated}}}


def _record(days_ago, share, training_status="not_triggered"):
    run_at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    return {"run_at": run_at, "drift": _drift(share), "training": {"status": training_status}}


def test_single_drifted_run_does_not_trigger():
    d = errors.should_retrain(_drift(0.9), history=[])
    assert not d["retrain"] and "streak 1/3" in d["notes"][0]


def test_persistent_drift_triggers():
    history = [_record(2, 0.8), _record(1, 0.7)]
    assert errors.should_retrain(_drift(0.9), history=history)["retrain"]


def test_streak_broken_by_calm_day():
    history = [_record(3, 0.8), _record(2, 0.1), _record(1, 0.7)]
    assert not errors.should_retrain(_drift(0.9), history=history)["retrain"]


def test_demo_drift_triggers_immediately():
    assert errors.should_retrain(_drift(0.9, simulated=True), history=[])["retrain"]


def test_cooldown_suppresses_but_force_overrides():
    history = [_record(3, 0.8, "trained"), _record(2, 0.8), _record(1, 0.8)]
    d = errors.should_retrain(_drift(0.9), history=history)
    assert not d["retrain"] and "cooldown" in d["notes"][-1]
    assert errors.should_retrain(_drift(0.9), history=history, force=True)["retrain"]


def test_calm_never_triggers():
    assert not errors.should_retrain(_drift(0.1), history=[])["retrain"]

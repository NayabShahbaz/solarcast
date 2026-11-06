"""[Member 1] Monitoring -> retraining.

1. Drift report: recent inputs vs the same season in the training data (Evidently).
2. Forecast errors, if forecasts and actuals exist for the same hours.
3. should_retrain() decides. If yes: training_flow -> promotion gate (Members 2 + 3).
   Evaluation, not drift, decides whether the new model is deployed.

Run locally:
  python -m solarcast.flows.retraining_flow              # normal check
  python -m solarcast.flows.retraining_flow --demo-drift # controlled drift demo (smog-like shift)
  python -m solarcast.flows.retraining_flow --force      # retrain regardless
"""

from __future__ import annotations

import argparse

from prefect import flow, get_run_logger, task

from solarcast.monitoring import drift, errors


@task(task_run_name="drift-report")
def run_drift(demo_drift: bool) -> dict:
    return drift.run_for_all_sites(simulate_drift=demo_drift)


@task(task_run_name="forecast-errors")
def run_errors() -> dict | None:
    return errors.run_for_all_sites()


@task(task_run_name="promotion-gate")
def promotion_gate(run_id: str) -> bool:
    from solarcast.models import promote
    try:
        ok = promote.compare_with_production(run_id)
        if ok:
            promote.promote(run_id)
        return ok
    except NotImplementedError as e:
        raise RuntimeError("models.promote is not implemented yet (Members 2 + 3)") from e


@flow(name="solarcast-monitor-and-retrain", log_prints=True)
def monitor_and_retrain_flow(force: bool = False, demo_drift: bool = False) -> dict:
    logger = get_run_logger()
    drift_summary = run_drift(demo_drift)
    error_summary = run_errors()
    decision = errors.should_retrain(
        drift_summary, error_summary, force=force, history=errors.load_history()
    )
    logger.info("retrain decision: %s", decision)

    training = {"status": "not_triggered"}
    if decision["retrain"]:
        from solarcast.flows.training_flow import TrainingNotAvailable, training_flow
        try:
            trained = training_flow(force=True)  # retrain even if the data is unchanged
            promoted = promotion_gate(trained["run_id"])
            training = {"status": "trained", "promoted": promoted, **trained}
            logger.info("candidate %s promoted: %s", trained["run_id"], promoted)
        except TrainingNotAvailable as e:
            # Expected until Member 2 delivers train/evaluate: trigger worked, nothing to run yet.
            training = {"status": "pending_member2", "detail": str(e)}
            logger.warning("retrain triggered but training is not available yet: %s", e)

    errors.write_monitoring_summary(drift_summary, error_summary, decision, training)
    return {"drift": drift_summary, "errors": error_summary, "decision": decision,
            "training": training}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--demo-drift", action="store_true")
    a = ap.parse_args()
    monitor_and_retrain_flow(force=a.force, demo_drift=a.demo_drift)

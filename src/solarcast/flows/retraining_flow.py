"""[Member 1] Monitoring -> retraining.

Drift/error check -> (if triggered) ingest + train -> hand candidate to the promotion gate
(models/promote.py, Members 2 + 3). Use force=True for the controlled drift demo.
"""

from prefect import flow


@flow(name="solarcast-monitor-and-retrain", log_prints=True)
def monitor_and_retrain_flow(force: bool = False):
    raise NotImplementedError


if __name__ == "__main__":
    monitor_and_retrain_flow()

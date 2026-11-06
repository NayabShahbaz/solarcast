"""[Member 2] Evaluation entry point - the `evaluate` stage in dvc.yaml.

Usage (normally via `dvc repro`):  python -m solarcast.models.evaluate

Reads every models/*/run.json, scores each model on the chronological TEST split
(MAE and RMSE in kWh, daylight hours, simulated vs real reported separately), logs the metrics
to each MLflow run, and writes reports/eval.json for DVC metrics and the promotion gate:
    {"baselines": {"mae_kwh": ..., "rmse_kwh": ...}, "tft": {...}, "best": "tft"}
"""

import argparse


def evaluate(run_id: str | None = None) -> dict:
    """Evaluate one run, or every model in models/*/run.json if run_id is None."""
    raise NotImplementedError


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=None, help="evaluate a single MLflow run instead")
    evaluate(p.parse_args().run_id)

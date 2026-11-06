"""[Member 2] Evaluation entry point: MAE / RMSE (kWh) on the chronological test split.

Usage: python -m solarcast.models.evaluate --run-id <mlflow_run_id>
Writes reports/eval_<run_id>.json, consumed by the promotion gate and CI.
"""

import argparse


def evaluate(run_id: str) -> dict:
    raise NotImplementedError


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    evaluate(p.parse_args().run_id)

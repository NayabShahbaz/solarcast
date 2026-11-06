"""[Member 2] Reproducible training entry point (called by Member 1's Prefect flow).

Usage: python -m solarcast.models.train --model tft
Logs params, DVC dataset version, MAE, RMSE and artifacts to MLflow; registers candidate TFT.
"""

import argparse


def train(model: str = "tft", dataset_version: str | None = None) -> str:
    """Train and return the MLflow run_id of the candidate."""
    raise NotImplementedError


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="tft", choices=["tft", "baselines", "chronos"])
    p.add_argument("--dataset-version", default=None)
    a = p.parse_args()
    train(a.model, a.dataset_version)

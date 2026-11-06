"""[Member 2] Training entry point - the `train_baseline` / `train_tft` stages in dvc.yaml.

Usage (normally via `dvc repro`):
    python -m solarcast.models.train --model baselines
    python -m solarcast.models.train --model tft

Contract with the pipeline (Member 1):
- read data/processed/hourly.parquet; it is already validated by the `validate` stage
- chronological train/val/test split from params.yaml -> split; windows from -> window
- log params, metrics, artifacts and the dataset version (git commit of dvc.lock) to the
  DagsHub MLflow server from .env
- write models/<model>/ (model files + run.json {"run_id", "model", "dataset_version"})
- tft only: register the model in the MLflow Model Registry as `solarcast-tft`
"""

import argparse

MODELS = ["baselines", "tft", "chronos"]


def train(model: str = "tft", dataset_version: str | None = None) -> str:
    """Train, write models/<model>/run.json, and return the MLflow run_id."""
    raise NotImplementedError


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="tft", choices=MODELS)
    p.add_argument("--dataset-version", default=None)
    a = p.parse_args()
    train(a.model, a.dataset_version)

"""[Member 1 + 2] Runs Member 2's training and evaluation entry points under Prefect.

Contract with Member 2 (src/solarcast/models):
  train(model="tft", dataset_version=<git commit of hourly.parquet.dvc>) -> mlflow run_id
  evaluate(run_id) -> {"mae_kwh": float, "rmse_kwh": float, ...}

Run locally: python -m solarcast.flows.training_flow
"""

from __future__ import annotations

import subprocess

from prefect import flow, get_run_logger, task

from solarcast.config import ROOT
from solarcast.data.pipeline import PROCESSED_FILE


class TrainingNotAvailable(RuntimeError):
    """Member 2's entry points aren't implemented yet (expected until week 2-3)."""


def dataset_version() -> str | None:
    """Git commit that last changed the DVC pointer of the processed dataset."""
    dvc_file = PROCESSED_FILE.with_suffix(PROCESSED_FILE.suffix + ".dvc")
    try:
        out = subprocess.run(
            ["git", "log", "-n", "1", "--format=%H", "--", str(dvc_file.relative_to(ROOT))],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _member2(fn_name: str):
    from solarcast.models import evaluate, train  # imported lazily: needs the [train] extras
    return {"train": train.train, "evaluate": evaluate.evaluate}[fn_name]


@task(task_run_name="train-{model}")
def run_training(model: str, version: str | None) -> str:
    if not PROCESSED_FILE.exists():
        raise FileNotFoundError(f"{PROCESSED_FILE} missing - run ingestion (history) or dvc pull")
    try:
        return _member2("train")(model=model, dataset_version=version)
    except NotImplementedError as e:
        raise TrainingNotAvailable("models.train.train() is not implemented yet (Member 2)") from e


@task(task_run_name="evaluate-{run_id}")
def run_evaluation(run_id: str) -> dict:
    try:
        return _member2("evaluate")(run_id)
    except NotImplementedError as e:
        raise TrainingNotAvailable(
            "models.evaluate.evaluate() is not implemented yet (Member 2)"
        ) from e


@flow(name="solarcast-training", log_prints=True)
def training_flow(model: str = "tft") -> dict:
    logger = get_run_logger()
    version = dataset_version()
    if version is None:
        logger.warning("processed dataset is not DVC-committed - run will not be reproducible")
    run_id = run_training(model, version)
    metrics = run_evaluation(run_id)
    logger.info("candidate %s on dataset %s: %s", run_id, version, metrics)
    return {"run_id": run_id, "dataset_version": version, "metrics": metrics}


if __name__ == "__main__":
    training_flow()

"""[Member 1 + 2] Runs the training part of dvc.yaml under Prefect.

  dvc repro evaluate      -> (data stages if needed) -> train_baseline, train_tft -> evaluate
  force=True (retraining) -> retrain both models even if their inputs didn't change

Contract with Member 2 (see src/solarcast/models/train.py and evaluate.py):
  models/<model>/run.json  {"run_id", "model", "dataset_version"}
  reports/eval.json        {"<model>": {"mae_kwh", "rmse_kwh"}, "best": ...}

Run locally: python -m solarcast.flows.training_flow [--force]
"""

from __future__ import annotations

import argparse
import json

from prefect import flow, get_run_logger, task

from solarcast.config import MODELS_DIR, REPORTS_DIR
from solarcast.flows import _dvc

EVAL_REPORT = REPORTS_DIR / "eval.json"
TRAIN_STAGES = ("train_baseline", "train_tft")


class TrainingNotAvailable(RuntimeError):
    """Member 2's entry points aren't implemented yet (expected until they land)."""


def _repro(*args: str) -> str:
    try:
        return _dvc.run("repro", *args)
    except _dvc.DvcError as e:
        if "NotImplementedError" in e.output:
            raise TrainingNotAvailable(
                "training/evaluation not implemented yet (Member 2): " + " ".join(args)
            ) from e
        raise


@task(task_run_name="dvc-repro-training")
def repro_training(force: bool) -> str:
    out = ""
    if force:  # -s: only this stage; -f: even though nothing changed
        for stage in TRAIN_STAGES:
            out += _repro("--force", "--single-item", stage)
    return out + _repro("evaluate")


@flow(name="solarcast-training", log_prints=True)
def training_flow(force: bool = False) -> dict:
    logger = get_run_logger()
    logger.info("dvc repro:\n%s", repro_training(force).strip())
    run = json.loads((MODELS_DIR / "tft" / "run.json").read_text(encoding="utf-8"))
    metrics = json.loads(EVAL_REPORT.read_text(encoding="utf-8"))
    version = _dvc.dataset_version()
    logger.info("candidate %s on dataset %s: %s", run["run_id"], version, metrics)
    return {"run_id": run["run_id"], "dataset_version": version, "metrics": metrics}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    training_flow(force=ap.parse_args().force)

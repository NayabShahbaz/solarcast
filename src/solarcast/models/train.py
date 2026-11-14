"""Repeatable training entry point with remote MLflow tracking."""

import argparse
import hashlib
import json
import os
import subprocess
import sys

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd

from solarcast.config import MODELS_DIR, PROCESSED_DIR, ROOT, params
from solarcast.features.calendar import add_calendar_features
from solarcast.features.windows import make_windows
from solarcast.models.baselines import FEATURES, train_baselines


def load_windows():
    """Build complete windows and assign them by forecast target dates."""
    settings = params()
    df = pd.read_parquet(PROCESSED_DIR / "hourly.parquet")
    df = add_calendar_features(df)

    windows = make_windows(
        df,
        history_hours=settings["window"]["history_hours"],
        horizon_hours=settings["window"]["horizon_hours"],
    )

    train_stop = (
        pd.Timestamp(settings["split"]["train_end"], tz="UTC")
        + pd.Timedelta(days=1)
    )
    val_stop = (
        pd.Timestamp(settings["split"]["val_end"], tz="UTC")
        + pd.Timedelta(days=1)
    )

    splits = {"train": [], "validation": [], "test": []}
    for window in windows:
        first = window["future"]["timestamp"].iloc[0]
        last = window["future"]["timestamp"].iloc[-1]

        if last < train_stop:
            splits["train"].append(window)
        elif first >= train_stop and last < val_stop:
            splits["validation"].append(window)
        elif first >= val_stop:
            splits["test"].append(window)

    if any(not windows for windows in splits.values()):
        raise ValueError("Every split must contain forecast windows.")

    return splits


def dataset_identity():
    """Record actual dataset bytes and the current Git revision."""
    path = PROCESSED_DIR / "hourly.parquet"
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return fingerprint, result.stdout.strip()


def configure_tracking():
    uri = os.getenv("MLFLOW_TRACKING_URI", "")
    if not uri.startswith("https://dagshub.com/"):
        raise ValueError("Configure remote DagsHub MLflow in .env.")

    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT", "solarcast"))


def train(model="baselines", dataset_version=None):
    if model == "tft":
        from solarcast.models.train_tft import train_tft
        return train_tft(dataset_version)

    configure_tracking()
    splits = load_windows()
    fingerprint, commit = dataset_identity()
    output = MODELS_DIR / model
    output.mkdir(parents=True, exist_ok=True)

    with mlflow.start_run(run_name="linear-regression-baseline") as run:
        mlflow.log_params({
            "model": "LinearRegression",
            "features": ",".join(FEATURES),
            "history_hours": params()["window"]["history_hours"],
            "horizon_hours": params()["window"]["horizon_hours"],
            "train_end": params()["split"]["train_end"],
            "val_end": params()["split"]["val_end"],
            "train_windows": len(splits["train"]),
            "validation_windows": len(splits["validation"]),
            "dataset_sha256": fingerprint,
        })
        mlflow.set_tags({
            "git_commit": commit,
            "dataset_type": "PVGIS simulated generation",
            "future_weather": "not used",
            "target_units": "kWh per kW",
        })

        result = train_baselines(
            splits["train"], splits["validation"]
        )["linear_regression"]

        estimator = result["model"]
        metrics = result["validation_metrics"]

        joblib.dump(estimator, output / "model.joblib")
        mlflow.log_metrics({
            "val_" + name: value for name, value in metrics.items()
        })
        mlflow.sklearn.log_model(
            estimator,
            artifact_path="model",
        )

        metadata = {
            "run_id": run.info.run_id,
            "model": model,
            "estimator": "linear_regression",
            "dataset_version": dataset_version or fingerprint,
            "dataset_sha256": fingerprint,
            "git_commit": commit,
            "validation_metrics": metrics,
        }
        (output / "run.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        mlflow.log_artifact(str(output / "run.json"))
        mlflow.log_artifact(str(ROOT / "params.yaml"))

        packages = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=True,
        )
        mlflow.log_text(packages.stdout, "environment.txt")

        print("Baseline training complete.")
        print("Validation metrics:", metrics)
        print("MLflow run ID:", run.info.run_id)
        print("Saved model:", output / "model.joblib")

        return run.info.run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", choices=["baselines", "tft"], default="baselines"
    )
    parser.add_argument("--dataset-version", default=None)
    args = parser.parse_args()
    train(args.model, args.dataset_version)
"""Train a small TFT and register it in remote MLflow."""

import json

import lightning.pytorch as pl
import mlflow
import mlflow.pytorch
import pandas as pd
import torch
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from mlflow.tracking import MlflowClient
from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet

from solarcast.config import MODELS_DIR, PROCESSED_DIR, ROOT, params
from solarcast.models.tft import build_dataset, build_model, prepare_frame


def date_stop(value):
    return pd.Timestamp(value, tz="UTC") + pd.Timedelta(days=1)


def hourly_index(timestamp):
    return int(timestamp.value // 3_600_000_000_000)


def select_daily_windows(dataset, start=None, stop=None):
    """Keep Lahore midnight forecasts wholly inside the requested split."""
    def keep(index):
        first = index["time_idx_first_prediction"]
        last = index["time_idx_last"]

        # UTC+5: local midnight corresponds to UTC hour 19.
        mask = (first + 5) % 24 == 0
        if start is not None:
            mask &= first >= hourly_index(start)
        if stop is not None:
            mask &= last < hourly_index(stop)
        return mask

    return dataset.filter(keep)


def train_tft(dataset_version=None):
    from solarcast.models.train import (
        configure_tracking,
        dataset_identity,
    )

    configure_tracking()
    pl.seed_everything(42, workers=True)
    torch.set_num_threads(4)

    settings = params()
    output = MODELS_DIR / "tft"
    output.mkdir(parents=True, exist_ok=True)

    df = prepare_frame(
        pd.read_parquet(PROCESSED_DIR / "hourly.parquet")
    )
    train_stop = date_stop(settings["split"]["train_end"])
    val_stop = date_stop(settings["split"]["val_end"])

    # Fit normalization and scaling on training rows only.
    base_dataset = build_dataset(
        df[df["timestamp"] < train_stop].copy()
    )
    train_dataset = select_daily_windows(
        base_dataset, stop=train_stop
    )

    # Reuse the fitted training preprocessing; include past context.
    validation_dataset = TimeSeriesDataSet.from_dataset(
        base_dataset,
        df[df["timestamp"] < val_stop].copy(),
        min_prediction_idx=hourly_index(train_stop),
        stop_randomization=True,
    )
    validation_dataset = select_daily_windows(
        validation_dataset, start=train_stop, stop=val_stop
    )

    print("TFT training windows:", len(train_dataset))
    print("TFT validation windows:", len(validation_dataset))

    batch_size = settings["tft"]["batch_size"]
    train_loader = train_dataset.to_dataloader(
        train=True,
        batch_size=batch_size,
        num_workers=0,
    )
    val_loader = validation_dataset.to_dataloader(
        train=False,
        batch_size=batch_size,
        num_workers=0,
    )

    fingerprint, commit = dataset_identity()

    with mlflow.start_run(run_name="tft-main-model") as run:
        mlflow.log_params({
            **settings["tft"],
            "seed": 42,
            "history_hours": settings["window"]["history_hours"],
            "horizon_hours": settings["window"]["horizon_hours"],
            "train_end": settings["split"]["train_end"],
            "val_end": settings["split"]["val_end"],
            "train_windows": len(train_dataset),
            "validation_windows": len(validation_dataset),
            "dataset_sha256": fingerprint,
        })
        mlflow.set_tags({
            "git_commit": commit,
            "dataset_type": "PVGIS simulated generation",
            "future_weather": "not used; calendar only",
            "target_units": "kWh per kW",
        })

        checkpoint = ModelCheckpoint(
            dirpath=str(output / "checkpoints"),
            filename="best",
            monitor="val_loss",
            mode="min",
            save_top_k=1,
        )
        early_stop = EarlyStopping(
            monitor="val_loss",
            patience=2,
            mode="min",
        )

        trainer = pl.Trainer(
            max_epochs=settings["tft"]["max_epochs"],
            accelerator="cpu",
            devices=1,
            logger=False,
            callbacks=[checkpoint, early_stop],
            gradient_clip_val=0.1,
            deterministic=True,
            enable_model_summary=False,
        )

        model = build_model(base_dataset)
        trainer.fit(
            model,
            train_dataloaders=train_loader,
            val_dataloaders=val_loader,
        )

        best = TemporalFusionTransformer.load_from_checkpoint(
            checkpoint.best_model_path,
            map_location="cpu",
        )
        best.cpu()
        best.eval()

        # Save everything needed for repeatable evaluation/loading.
        trainer.save_checkpoint(str(output / "last.ckpt"))
        best_checkpoint = output / "model.ckpt"
        import shutil
        shutil.copy2(checkpoint.best_model_path, best_checkpoint)

        torch.save(
            base_dataset.get_parameters(),
            output / "dataset_parameters.pt",
        )
        mlflow.log_metric(
            "val_quantile_loss",
            float(checkpoint.best_model_score),
        )
        mlflow.log_artifact(str(best_checkpoint), "checkpoint")
        mlflow.log_artifact(
            str(output / "dataset_parameters.pt"), "checkpoint"
        )
        mlflow.log_artifact(str(ROOT / "params.yaml"))

        model_name = "solarcast-tft"
        model_info = mlflow.pytorch.log_model(
            best,
            artifact_path="model",
            registered_model_name=model_name,
        )

        client = MlflowClient()
        versions = client.search_model_versions(
            f"name='{model_name}'"
        )
        matching = [
            version for version in versions
            if version.run_id == run.info.run_id
        ]
        if not matching:
            raise RuntimeError("Registered version was not found.")

        version = max(matching, key=lambda item: int(item.version))
        client.transition_model_version_stage(
            name=model_name,
            version=version.version,
            stage="Staging",
        )
        client.set_registered_model_alias(
            model_name, "staging", version.version
        )

        metadata = {
            "run_id": run.info.run_id,
            "model": "tft",
            "dataset_version": dataset_version or fingerprint,
            "dataset_sha256": fingerprint,
            "git_commit": commit,
            "registered_model": model_name,
            "registered_version": str(version.version),
            "model_uri": model_info.model_uri,
        }
        (output / "run.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        mlflow.log_artifact(str(output / "run.json"))

        print("TFT training complete.")
        print("MLflow run ID:", run.info.run_id)
        print("Registered model:", model_name)
        print("Version:", version.version)
        print("Stage: Staging")
        return run.info.run_id
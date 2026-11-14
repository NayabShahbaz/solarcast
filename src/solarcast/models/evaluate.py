"""Evaluate saved models and log results to their original MLflow runs."""

import argparse
import json

import joblib
import mlflow
import numpy as np
import pandas as pd

from solarcast.config import (
    MODELS_DIR,
    PROCESSED_DIR,
    REPORTS_DIR,
    params,
)
from solarcast.models.baselines import (
    predict_baseline,
    score_predictions,
)
from solarcast.models.train import configure_tracking, load_windows


def predict_tft(split):
    import torch
    from pytorch_forecasting import (
        TemporalFusionTransformer,
        TimeSeriesDataSet,
    )

    from solarcast.models.tft import prepare_frame
    from solarcast.models.train_tft import (
        date_stop,
        hourly_index,
        select_daily_windows,
    )

    torch.set_num_threads(4)
    folder = MODELS_DIR / "tft"
    df = prepare_frame(
        pd.read_parquet(PROCESSED_DIR / "hourly.parquet")
    )

    train_stop = date_stop(params()["split"]["train_end"])
    val_stop = date_stop(params()["split"]["val_end"])
    start = train_stop if split == "validation" else val_stop
    stop = val_stop if split == "validation" else None

    context = df if stop is None else df[df["timestamp"] < stop]
    saved_parameters = torch.load(
        folder / "dataset_parameters.pt",
        map_location="cpu",
        weights_only=False,
    )
    dataset = TimeSeriesDataSet.from_parameters(
        saved_parameters,
        context.copy(),
        min_prediction_idx=hourly_index(start),
        stop_randomization=True,
    )
    dataset = select_daily_windows(dataset, start=start, stop=stop)
    loader = dataset.to_dataloader(
        train=False,
        batch_size=params()["tft"]["batch_size"],
        num_workers=0,
    )

    model = TemporalFusionTransformer.load_from_checkpoint(
        str(folder / "model.ckpt"),
        map_location="cpu",
    )
    model.eval()

    quantiles = list(model.loss.quantiles)
    positions = [quantiles.index(q) for q in (0.1, 0.5, 0.9)]
    batches = []

    with torch.no_grad():
        for x, _ in loader:
            # TFT outputs are already returned to original per-kW units.
            prediction = model(x)["prediction"].cpu().numpy()
            index = dataset.x_to_index(x)
            times = x["decoder_time_idx"].cpu().numpy()
            horizon = times.shape[1]

            batch = pd.DataFrame({
                "series_id": np.repeat(
                    index["series_id"].to_numpy(), horizon
                ),
                "time_idx": times.reshape(-1),
            })

            for name, position in zip(
                ["p10_per_kw", "p50_per_kw", "p90_per_kw"],
                positions,
            ):
                batch[name] = prediction[:, :, position].reshape(-1)

            batches.append(batch)

    predicted = pd.concat(batches, ignore_index=True)
    actual = df[[
        "series_id", "time_idx", "timestamp", "site_id",
        "panel_capacity_kw", "generation_kwh", "ghi_wm2",
    ]]
    result = predicted.merge(
        actual,
        on=["series_id", "time_idx"],
        how="left",
        validate="one_to_one",
    )
    if result["generation_kwh"].isna().any():
        raise ValueError("Some TFT predictions have no matching actuals.")

    # Sort quantiles to remove crossings, then enforce physical bounds.
    values = np.sort(
        result[["p10_per_kw", "p50_per_kw", "p90_per_kw"]].to_numpy(),
        axis=1,
    )
    values = np.clip(values, 0, 1.1)
    values *= result["panel_capacity_kw"].to_numpy()[:, None]

    result[["p10_kwh", "predicted_kwh", "p90_kwh"]] = values
    return result.rename(columns={"generation_kwh": "actual_kwh"})


def summarize(predictions):
    all_hours = score_predictions(
        predictions["actual_kwh"], predictions["predicted_kwh"]
    )
    daylight = predictions[
        predictions["ghi_wm2"]
        >= params()["data"]["night_ghi_threshold_wm2"]
    ]
    daylight_metrics = score_predictions(
        daylight["actual_kwh"], daylight["predicted_kwh"]
    )
    per_kw = score_predictions(
        daylight["actual_kwh"] / daylight["panel_capacity_kw"],
        daylight["predicted_kwh"] / daylight["panel_capacity_kw"],
    )

    return {
        **daylight_metrics,
        "all_hours_mae_kwh": all_hours["mae_kwh"],
        "all_hours_rmse_kwh": all_hours["rmse_kwh"],
        "mae_per_kw": per_kw["mae_kwh"],
        "rmse_per_kw": per_kw["rmse_kwh"],
        "hours": len(predictions),
        "daylight_hours": len(daylight),
    }


def evaluate(run_id=None):
    configure_tracking()
    windows = load_windows()
    output = REPORTS_DIR / "evaluation"
    output.mkdir(parents=True, exist_ok=True)

    report = {}
    expected_keys = {}

    for name in ["baselines", "tft"]:
        folder = MODELS_DIR / name
        metadata = json.loads(
            (folder / "run.json").read_text(encoding="utf-8")
        )
        if run_id is not None and metadata["run_id"] != run_id:
            continue

        with mlflow.start_run(run_id=metadata["run_id"]):
            for split in ["validation", "test"]:
                if name == "baselines":
                    model = joblib.load(folder / "model.joblib")
                    predictions = predict_baseline(model, windows[split])
                else:
                    predictions = predict_tft(split)

                # Ensure both models are evaluated on identical target hours.
                keys = set(zip(
                    predictions["site_id"],
                    predictions["timestamp"],
                ))
                if len(keys) != len(predictions):
                    raise ValueError("Duplicate evaluation target hours.")
                if split in expected_keys and keys != expected_keys[split]:
                    raise ValueError("Models have different evaluation hours.")
                expected_keys[split] = keys

                metrics = summarize(predictions)
                prefix = "val" if split == "validation" else "test"
                logged = {
                    f"{prefix}_{key}": value
                    for key, value in metrics.items()
                    if key not in ("mae_kwh", "rmse_kwh")
                }
                logged[f"{prefix}_daylight_mae_kwh"] = metrics["mae_kwh"]
                logged[f"{prefix}_daylight_rmse_kwh"] = metrics["rmse_kwh"]
                mlflow.log_metrics(logged)

                path = output / f"{name}_{split}.csv"
                predictions.to_csv(path, index=False)
                mlflow.log_artifact(str(path), "evaluation")

                if split == "test":
                    report[name] = metrics
                print(name, split, metrics)

    if not report:
        raise ValueError("No matching saved model runs found.")

    report["best"] = min(
        report, key=lambda name: report[name]["mae_kwh"]
    )
    report["dataset_type"] = "PVGIS simulated generation"
    report["primary_metrics"] = "Daylight-hour MAE and RMSE in kWh"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "eval.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("\nSaved reports/eval.json")
    print("Best test daylight MAE:", report["best"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    evaluate(parser.parse_args().run_id)
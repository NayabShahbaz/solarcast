"""Linear Regression using calendar and historical generation."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "hour_sin", "hour_cos", "year_sin", "year_cos",
    "generation_yesterday", "generation_last_week",
]


def window_features(windows):
    features, targets, records = [], [], []

    for window in windows:
        history = window["history"]
        future = window["future"]

        if len(history) < 168 or len(future) != 24:
            raise ValueError("Expected 168h history and 24h horizon.")

        past = (
            history["generation_kwh"] / history["panel_capacity_kw"]
        ).to_numpy()

        for hour, (_, row) in enumerate(future.iterrows()):
            capacity = float(row["panel_capacity_kw"])
            if capacity <= 0:
                raise ValueError("Panel capacity must be positive.")

            features.append([
                row["hour_sin"], row["hour_cos"],
                row["year_sin"], row["year_cos"],
                past[-24 + hour], past[-168 + hour],
            ])
            targets.append(float(row["generation_kwh"]) / capacity)
            records.append({
                "timestamp": row["timestamp"],
                "site_id": window["site_id"],
                "panel_capacity_kw": capacity,
                "actual_kwh": float(row["generation_kwh"]),
                "ghi_wm2": float(row["ghi_wm2"]),
            })

    if not records:
        raise ValueError("No complete forecasting windows.")

    return (
        pd.DataFrame(features, columns=FEATURES),
        np.asarray(targets),
        pd.DataFrame(records),
    )


def score_predictions(actual_kwh, predicted_kwh):
    error = np.asarray(predicted_kwh) - np.asarray(actual_kwh)
    if error.size == 0:
        raise ValueError("No predictions to evaluate.")
    return {
        "mae_kwh": float(np.mean(np.abs(error))),
        "rmse_kwh": float(np.sqrt(np.mean(error ** 2))),
    }


def predict_baseline(model, windows):
    features, _, records = window_features(windows)
    per_kw = np.clip(model.predict(features), 0, 1.1)
    records["predicted_kwh"] = (
        per_kw * records["panel_capacity_kw"].to_numpy()
    )
    return records


def train_baselines(train_windows, val_windows):
    features, targets, _ = window_features(train_windows)
    model = make_pipeline(StandardScaler(), LinearRegression())
    model.fit(features, targets)

    predictions = predict_baseline(model, val_windows)
    return {
        "linear_regression": {
            "model": model,
            "validation_metrics": score_predictions(
                predictions["actual_kwh"],
                predictions["predicted_kwh"],
            ),
        }
    }
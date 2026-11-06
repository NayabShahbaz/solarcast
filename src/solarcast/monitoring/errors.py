"""[Member 1] Forecast vs actual once real generation arrives (MAE / RMSE in kWh)."""

import pandas as pd


def compute_forecast_errors(forecasts: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError


def should_retrain(drift_summary: dict, error_summary: dict | None = None) -> bool:
    """Retraining trigger. Promotion is still decided by evaluation (Member 2), not here."""
    raise NotImplementedError

"""[Member 1] Evidently data drift: current inputs vs data/reference (training window)."""

import pandas as pd


def run_drift_report(reference: pd.DataFrame, current: pd.DataFrame) -> dict:
    """Save HTML + JSON to reports/monitoring/ (and S3) and return a summary dict:

    {"run_at", "dataset_drift": bool, "drift_share": float, "drifted_columns": [...]}
    The dashboard (Member 3) reads this JSON - keep the keys stable.
    """
    raise NotImplementedError

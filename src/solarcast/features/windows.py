"""[Member 2] 7-day (168h) history windows -> 24h targets, chronological train/val/test splits.

Fit any scaling ONLY on the training split and save it with the model.
"""

import pandas as pd


def chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raise NotImplementedError


def make_windows(df: pd.DataFrame, history_hours: int = 168, horizon_hours: int = 24):
    raise NotImplementedError

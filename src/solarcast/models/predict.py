"""[Member 2] Deployment-ready inference used by the API (Member 3). CPU only.

Agreed interface - change only via a PR reviewed by Members 2 and 3.
"""

import pandas as pd


def load_model(model_uri: str):
    """Load TFT checkpoint + saved preprocessing (e.g. models:/solarcast-tft/Production)."""
    raise NotImplementedError


def predict(model, history: pd.DataFrame, future_weather: pd.DataFrame, site: dict) -> pd.DataFrame:
    """history: >= 168 hourly rows; future_weather: 24 rows.

    Returns 24 rows: [timestamp, p10_kwh, p50_kwh, p90_kwh].
    """
    raise NotImplementedError

"""[Member 1] Open-Meteo weather.

History : https://archive-api.open-meteo.com/v1/archive
Forecast: https://api.open-meteo.com/v1/forecast   (next-day inputs at prediction time)
"""

import pandas as pd


def fetch_history(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    raise NotImplementedError


def fetch_forecast(lat: float, lon: float, hours: int = 24) -> pd.DataFrame:
    """Next-day hourly forecast used as future known inputs for the TFT."""
    raise NotImplementedError

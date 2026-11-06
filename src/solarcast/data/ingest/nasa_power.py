"""[Member 1] NASA POWER hourly irradiance + temperature.

API: https://power.larc.nasa.gov/api/temporal/hourly/point
"""

import pandas as pd


def fetch_hourly(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """Return raw hourly NASA POWER data (ALLSKY_SFC_SW_DWN, T2M, ...) for the point."""
    raise NotImplementedError

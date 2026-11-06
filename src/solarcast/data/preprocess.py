"""[Member 1] Raw -> processed hourly dataset matching solarcast.schemas.PROCESSED_COLUMNS.

Rules (agree with Member 2, document in docs/data_contract.md):
- convert all timestamps to UTC, floor to the hour, hourly frequency
- standardise units (W -> kW, Wh -> kWh, J/m^2 -> W/m^2)
- drop duplicate timestamps (keep last), clip/flag invalid values (negative generation, GHI)
- short gaps (<= params.data.max_gap_hours_interpolate) interpolated, long gaps flagged/dropped
- generation forced to 0 at night (GHI below threshold)
- keep source / is_simulated so simulated and real results can be reported separately
"""

import pandas as pd


def align_weather_and_generation(weather: pd.DataFrame, generation: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError


def clean_hourly(df: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError


def build_processed_dataset() -> pd.DataFrame:
    """Entry point: read data/raw, write data/processed/hourly.parquet."""
    raise NotImplementedError

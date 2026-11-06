"""[Member 1] Pandera checks run before training and before prediction.

Required columns, dtypes, nulls and sensible ranges for Lahore.
"""

import pandas as pd


def validate_processed(df: pd.DataFrame) -> pd.DataFrame:
    """Raise pandera.errors.SchemaErrors (lazy=True) listing every failing check."""
    # TODO: pandera DataFrameModel built from solarcast.schemas, e.g.
    #   0 <= generation_kwh <= panel_capacity_kw * 1.1
    #   0 <= ghi_wm2 <= 1400, -5 <= temp_c <= 55, 0 <= cloud_cover_pct <= 100
    #   timestamp unique per site, hourly, tz-aware UTC
    raise NotImplementedError

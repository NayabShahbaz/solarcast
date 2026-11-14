"""Calendar features calculated in Lahore local time."""

import numpy as np
import pandas as pd


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    local_time = df["timestamp"].dt.tz_convert("Asia/Karachi")

    df["hour"] = local_time.dt.hour
    df["day_of_year"] = local_time.dt.dayofyear
    df["month"] = local_time.dt.month
    df["weekday"] = local_time.dt.dayofweek

    # Cyclic features keep adjacent hours/seasons close together.
    # For example, 23:00 and 00:00 are only one hour apart.
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    days_in_year = np.where(local_time.dt.is_leap_year, 366, 365)
    df["year_sin"] = np.sin(
        2 * np.pi * (df["day_of_year"] - 1) / days_in_year
    )
    df["year_cos"] = np.cos(
        2 * np.pi * (df["day_of_year"] - 1) / days_in_year
    )

    return df
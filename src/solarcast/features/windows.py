"""Chronological splits and complete day-ahead forecasting windows."""

import pandas as pd

from solarcast.config import params


def chronological_split(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split by UTC dates from params.yaml, including each cutoff day."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    settings = params()["split"]
    train_stop = (
        pd.Timestamp(settings["train_end"], tz="UTC")
        + pd.Timedelta(days=1)
    )
    val_stop = (
        pd.Timestamp(settings["val_end"], tz="UTC")
        + pd.Timedelta(days=1)
    )

    train = df[df["timestamp"] < train_stop].copy()
    val = df[
        (df["timestamp"] >= train_stop)
        & (df["timestamp"] < val_stop)
    ].copy()
    test = df[df["timestamp"] >= val_stop].copy()

    return train, val, test


def make_windows(
    df: pd.DataFrame,
    history_hours: int = 168,
    horizon_hours: int = 24,
):
    """Return complete windows forecasting from midnight Lahore time.

    Each result contains a history dataframe and a future dataframe.
    Future generation is a label for evaluation, never an input feature.
    """
    if history_hours < 1 or horizon_hours < 1:
        raise ValueError("History and horizon must be positive.")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    if df.duplicated(["site_id", "timestamp"]).any():
        raise ValueError("Duplicate timestamps found within a site.")

    windows = []
    total_hours = history_hours + horizon_hours
    timezone = params()["data"].get("timezone", "Asia/Karachi")

    for site_id, site in df.groupby("site_id"):
        site = site.sort_values("timestamp").reset_index(drop=True)

        # A new segment starts whenever an hour is missing.
        segments = (
            site["timestamp"].diff() != pd.Timedelta(hours=1)
        ).cumsum()
        local_time = site["timestamp"].dt.tz_convert(timezone)

        for start in range(
            history_hours, len(site) - horizon_hours + 1
        ):
            # One day-ahead forecast per local calendar day.
            if local_time.iloc[start].hour != 0:
                continue

            left = start - history_hours
            right = start + horizon_hours

            if segments.iloc[left] != segments.iloc[right - 1]:
                continue

            block = site.iloc[left:right]
            if len(block) != total_hours:
                continue

            windows.append({
                "site_id": str(site_id),
                "history": site.iloc[left:start].copy(),
                "future": site.iloc[start:right].copy(),
            })

    return windows
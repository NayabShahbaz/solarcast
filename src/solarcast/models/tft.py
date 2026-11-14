"""Small Temporal Fusion Transformer for day-ahead forecasting."""

from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data import TorchNormalizer
from pytorch_forecasting.metrics import QuantileLoss

from solarcast.config import params
from solarcast.features.calendar import add_calendar_features

CALENDAR = ["hour_sin", "hour_cos", "year_sin", "year_cos"]
PAST_WEATHER = [
    "ghi_wm2",
    "gti_wm2",
    "temp_c",
    "cloud_cover_pct",
    "rel_humidity_pct",
    "wind_speed_ms",
]


def prepare_frame(df):
    """Prepare model inputs without fitting preprocessing."""
    df = add_calendar_features(df)
    df = df.sort_values(["site_id", "timestamp"]).reset_index(drop=True)
    df["site_id"] = df["site_id"].astype(str)

    if df.duplicated(["site_id", "timestamp"]).any():
        raise ValueError("Duplicate site timestamps.")

    if (df["panel_capacity_kw"] <= 0).any():
        raise ValueError("Panel capacity must be positive.")

    df["target_per_kw"] = (
        df["generation_kwh"] / df["panel_capacity_kw"]
    ).astype(float)

    # Absolute hourly index: gaps remain visible.
    df["time_idx"] = (
        df["timestamp"].astype("int64") // 3_600_000_000_000
    ).astype("int64")

    # Separate continuous segments so windows never cross missing hours.
    gaps = df.groupby("site_id")["time_idx"].diff().ne(1)
    df["segment"] = gaps.groupby(df["site_id"]).cumsum().astype(int)
    df["series_id"] = df["site_id"] + "_" + df["segment"].astype(str)

    for column in CALENDAR + PAST_WEATHER:
        df[column] = df[column].astype(float)

    return df


def build_dataset(df):
    """Call with TRAINING rows only; scalers are fitted here."""
    settings = params()["window"]

    return TimeSeriesDataSet(
        df,
        time_idx="time_idx",
        target="target_per_kw",
        group_ids=["series_id"],
        static_categoricals=["site_id"],
        time_varying_known_reals=CALENDAR,
        time_varying_unknown_reals=["target_per_kw"] + PAST_WEATHER,
        max_encoder_length=settings["history_hours"],
        min_encoder_length=settings["history_hours"],
        max_prediction_length=settings["horizon_hours"],
        min_prediction_length=settings["horizon_hours"],
        target_normalizer=TorchNormalizer(method="standard"),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
        allow_missing_timesteps=False,
    )


def build_model(dataset):
    settings = params()["tft"]

    return TemporalFusionTransformer.from_dataset(
        dataset,
        hidden_size=settings["hidden_size"],
        attention_head_size=settings["attention_head_size"],
        dropout=settings["dropout"],
        learning_rate=settings["learning_rate"],
        output_size=len(settings["quantiles"]),
        loss=QuantileLoss(quantiles=settings["quantiles"]),
        reduce_on_plateau_patience=2,
        log_interval=-1,
    )
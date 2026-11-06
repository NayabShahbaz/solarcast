"""[Member 1] Pandera checks, run before training and before prediction.

Two schemas:
- PROCESSED: the training dataset (target + weather + metadata), built from solarcast.schemas.
- WEATHER_INPUT: weather only, for next-day forecast inputs where there is no generation yet.
All checks run lazily, so one failure report lists every problem at once.
"""

from __future__ import annotations

import pandas as pd

try:  # pandera >= 0.24 moved the pandas API here
    import pandera.pandas as pa
except ImportError:  # pragma: no cover
    import pandera as pa

from solarcast import schemas as S
from solarcast.config import params
from solarcast.data.preprocess import VALID_RANGES


def _weather_columns() -> dict[str, pa.Column]:
    return {
        col: pa.Column(float, pa.Check.in_range(lo, hi), nullable=False)
        for col, (lo, hi) in VALID_RANGES.items()
    }


def _utc_hourly(ts: pd.Series) -> bool:
    return (
        isinstance(ts.dtype, pd.DatetimeTZDtype)
        and str(ts.dt.tz) == "UTC"
        and bool((ts == ts.dt.floor("h")).all())
    )


def _capacity_check(df: pd.DataFrame) -> pd.Series:
    margin = params()["data"]["generation_capacity_margin"]
    return df[S.GENERATION_KWH] <= df[S.PANEL_CAPACITY_KW] * margin


def _night_zero_check(df: pd.DataFrame) -> pd.Series:
    night = df[S.GHI] < params()["data"]["night_ghi_threshold_wm2"]
    return ~night | (df[S.GENERATION_KWH] == 0)


PROCESSED = pa.DataFrameSchema(
    {
        S.TIMESTAMP: pa.Column(
            "datetime64[ns, UTC]",
            pa.Check(_utc_hourly, element_wise=False, error="timestamp must be UTC start-of-hour"),
        ),
        S.SITE_ID: pa.Column(str, pa.Check.str_length(min_value=1)),
        S.SOURCE: pa.Column(str, pa.Check.isin(S.SOURCES)),
        S.IS_SIMULATED: pa.Column(bool),
        S.GENERATION_KWH: pa.Column(float, pa.Check.ge(0)),
        **_weather_columns(),
        S.PANEL_CAPACITY_KW: pa.Column(float, pa.Check.gt(0)),
        S.IS_IMPUTED: pa.Column(bool),
    },
    checks=[
        pa.Check(_capacity_check, error="generation_kwh exceeds panel capacity * margin"),
        pa.Check(_night_zero_check, error="generation must be 0 when GHI is below threshold"),
        pa.Check(
            lambda df: ~df.duplicated([S.SITE_ID, S.TIMESTAMP]),
            error="duplicate (site_id, timestamp)",
        ),
        pa.Check(
            lambda df: (df[S.SOURCE] == "inverter") != df[S.IS_SIMULATED],
            error="is_simulated must be False only for inverter data",
        ),
    ],
    strict=True,
    ordered=False,
    coerce=False,
    name="processed_hourly",
)

WEATHER_INPUT = pa.DataFrameSchema(
    {
        S.TIMESTAMP: pa.Column(
            "datetime64[ns, UTC]",
            pa.Check(_utc_hourly, element_wise=False, error="timestamp must be UTC start-of-hour"),
            unique=True,
        ),
        **_weather_columns(),
    },
    strict=False,
    name="weather_input",
)


def validate_processed(df: pd.DataFrame) -> pd.DataFrame:
    """Raise pandera.errors.SchemaErrors (lazy) listing every failing check."""
    return PROCESSED.validate(df, lazy=True)


def validate_weather_input(df: pd.DataFrame, expected_rows: int | None = None) -> pd.DataFrame:
    out = WEATHER_INPUT.validate(df, lazy=True)
    if expected_rows is not None and len(out) != expected_rows:
        raise ValueError(f"weather input: expected {expected_rows} rows, got {len(out)}")
    return out


def failure_summary(err: Exception) -> str:
    """Readable one-line-per-problem summary of a SchemaErrors, for Prefect logs."""
    cases = getattr(err, "failure_cases", None)
    if cases is None:
        return str(err)
    lines = (
        cases.groupby(["column", "check"], dropna=False)
        .size()
        .reset_index(name="n")
        .itertuples(index=False)
    )
    return "\n".join(f"- {c.column or '<frame>'}: {c.check} ({c.n} rows)" for c in lines)

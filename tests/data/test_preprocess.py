import numpy as np
import pandas as pd

from solarcast import schemas as S
from solarcast.data import preprocess


def test_interpolate_only_short_gaps():
    s = pd.Series([1.0, np.nan, 3.0, np.nan, np.nan, np.nan, np.nan, 8.0, np.nan])
    filled, mask = preprocess.interpolate_short_gaps(s, max_gap=3)
    assert filled[1] == 2.0 and mask[1]
    assert filled[3:7].isna().all()  # 4-hour gap is too long
    assert np.isnan(filled[8])  # trailing gap has no right-hand neighbour
    assert mask.sum() == 1


def test_build_site_dataset_matches_contract(weather_raw, generation_raw, site):
    df = preprocess.build_site_dataset(weather_raw, generation_raw, site)
    assert list(df.columns) == S.PROCESSED_COLUMNS
    assert len(df) == len(weather_raw)
    assert str(df[S.TIMESTAMP].dt.tz) == "UTC"
    assert not df.isna().any().any()


def test_duplicates_dropped_keep_last(weather_raw, generation_raw, site):
    dup = generation_raw.iloc[[5]].assign(**{S.GENERATION_KWH: 1.234})
    gen = pd.concat([generation_raw, dup])
    df = preprocess.build_site_dataset(weather_raw, gen, site)
    assert df[S.TIMESTAMP].is_unique
    ts = generation_raw[S.TIMESTAMP].iloc[5]
    row = df[df[S.TIMESTAMP] == ts]
    # hour 5 UTC is daylight, so the duplicate's value must win
    assert row[S.GENERATION_KWH].item() == 1.234


def test_short_gap_imputed_and_flagged(weather_raw, generation_raw, site):
    w = weather_raw.drop(index=[30, 31])  # 2-hour gap
    df = preprocess.build_site_dataset(w, generation_raw, site)
    assert len(df) == len(weather_raw)
    assert df[S.IS_IMPUTED].sum() == 2


def test_long_gap_rows_dropped(weather_raw, generation_raw, site):
    w = weather_raw.drop(index=range(40, 46))  # 6-hour gap > limit of 3
    df = preprocess.build_site_dataset(w, generation_raw, site)
    assert len(df) == len(weather_raw) - 6


def test_invalid_values_nulled_then_handled(weather_raw, generation_raw, site):
    g = generation_raw.copy()
    g.loc[50, S.GENERATION_KWH] = 999.0  # above capacity -> invalid -> interpolated
    g.loc[51, S.GENERATION_KWH] = -5.0  # negative -> invalid -> interpolated
    df = preprocess.build_site_dataset(weather_raw, g, site)
    assert df[S.GENERATION_KWH].max() <= site["panel_capacity_kw"] * 1.1
    assert df[S.GENERATION_KWH].min() >= 0


def test_night_generation_forced_to_zero(weather_raw, generation_raw, site):
    g = generation_raw.copy()
    night = weather_raw[S.GHI] == 0
    g.loc[night, S.GENERATION_KWH] = 0.3
    df = preprocess.build_site_dataset(weather_raw, g, site)
    assert (df.loc[df[S.GHI] < 5, S.GENERATION_KWH] == 0).all()

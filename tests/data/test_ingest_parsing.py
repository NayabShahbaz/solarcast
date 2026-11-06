"""Parsing tests against payloads shaped like the real APIs (no network)."""

import pandas as pd
import pytest

from solarcast import schemas as S
from solarcast.data.ingest import _http, nasa_power, open_meteo, pv_model, pvgis


def test_pvgis_midpoint_times_floored_and_watts_to_kwh(monkeypatch, site):
    payload = {
        "outputs": {
            "hourly": [
                {"time": "20230101:0630", "P": 2500.0},
                {"time": "20230101:0730", "P": 4000.0},
            ]
        }
    }
    monkeypatch.setattr(pvgis, "get_json", lambda *a, **k: payload)
    df = pvgis.fetch_simulated_pv(site, 2023, 2023)
    assert df[S.TIMESTAMP].iloc[0] == pd.Timestamp("2023-01-01 06:00", tz="UTC")
    assert df[S.GENERATION_KWH].tolist() == [2.5, 4.0]
    assert df[S.IS_SIMULATED].all() and (df[S.SOURCE] == "pvgis").all()


def test_pvgis_rejects_years_outside_coverage(site):
    with pytest.raises(_http.SourceError):
        pvgis.fetch_simulated_pv(site, 2023, 2024)


def test_open_meteo_shifts_to_hour_start(monkeypatch, site):
    payload = {
        "hourly": {
            "time": ["2023-06-01T01:00", "2023-06-01T02:00"],
            "shortwave_radiation": [14.0, 114.0],
            "global_tilted_irradiance": [10.0, 120.0],
            "temperature_2m": [30.0, 31.0],
            "cloud_cover": [0, 0],
            "relative_humidity_2m": [40, 38],
            "wind_speed_10m": [1.0, 1.2],
        }
    }
    monkeypatch.setattr(open_meteo, "get_json", lambda *a, **k: payload)
    df = open_meteo.fetch_history(site, "2023-06-01", "2023-06-01")
    assert df[S.TIMESTAMP].iloc[0] == pd.Timestamp("2023-06-01 00:00", tz="UTC")
    assert list(df.columns) == [S.TIMESTAMP, *S.WEATHER_COLUMNS]


def test_open_meteo_year_chunks():
    chunks = open_meteo._year_chunks("2020-06-01", "2022-02-01")
    assert chunks == [
        ("2020-06-01", "2020-12-31"),
        ("2021-01-01", "2021-12-31"),
        ("2022-01-01", "2022-02-01"),
    ]


def test_next_day_window_is_local_tomorrow(weather_raw):
    today = pd.Timestamp("2023-01-03", tz="Asia/Karachi")
    out = open_meteo.next_day_window(weather_raw, today)
    assert len(out) == 24
    # local midnight Jan 4 PKT = 19:00 UTC Jan 3
    assert out[S.TIMESTAMP].iloc[0] == pd.Timestamp("2023-01-03 19:00", tz="UTC")


def test_nasa_fill_values_become_nan(monkeypatch, site):
    payload = {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {"2023010106": 500.0, "2023010107": -999.0},
                "T2M": {"2023010106": 12.0, "2023010107": 13.0},
                "RH2M": {"2023010106": 60.0, "2023010107": 58.0},
                "WS10M": {"2023010106": 1.5, "2023010107": 1.7},
            }
        }
    }
    monkeypatch.setattr(nasa_power, "get_json", lambda *a, **k: payload)
    df = nasa_power.fetch_hourly(site, "2023-01-01", "2023-01-01")
    assert df[S.GHI].isna().sum() == 1


def test_pv_model_calibration_recovers_scale(weather_raw, site):
    raw = pv_model._raw_estimate(weather_raw, site["panel_capacity_kw"])
    pvgis_like = pd.DataFrame({S.TIMESTAMP: weather_raw[S.TIMESTAMP],
                               S.GENERATION_KWH: 0.82 * raw})
    k = pv_model.calibrate(weather_raw, pvgis_like, site["panel_capacity_kw"])
    assert k == pytest.approx(0.82, abs=1e-3)
    est = pv_model.estimate_generation(weather_raw, site, k)
    assert (est[S.GENERATION_KWH] >= 0).all()
    assert (est[S.SOURCE] == "pv_model").all()

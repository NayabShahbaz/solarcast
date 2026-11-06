import numpy as np
import pandas as pd
import pytest

from solarcast import schemas as S

SITE = {
    "site_id": "test_site",
    "source": "pvgis",
    "is_simulated": True,
    "latitude": 31.52,
    "longitude": 74.36,
    "panel_capacity_kw": 10.0,
    "tilt_deg": 20,
    "azimuth_deg": 180,
    "system_loss_pct": 14,
}


@pytest.fixture
def site():
    return dict(SITE)


def _sun(ts: pd.DatetimeIndex) -> np.ndarray:
    """Crude clear-sky shape for Lahore: daylight ~01-13 UTC, peak ~07 UTC."""
    hour = ts.hour.to_numpy()
    return np.clip(np.sin((hour - 1) / 12 * np.pi), 0, None) * (hour >= 1) * (hour <= 13)


@pytest.fixture
def weather_raw():
    ts = pd.date_range("2023-01-01", periods=24 * 10, freq="h", tz="UTC")
    sun = _sun(ts)
    return pd.DataFrame(
        {
            S.TIMESTAMP: ts,
            S.GHI: 800 * sun,
            S.GTI: 900 * sun,
            S.TEMP: 15 + 10 * sun,
            S.CLOUD_COVER: 20.0,
            S.REL_HUMIDITY: 50.0,
            S.WIND_SPEED: 2.0,
        }
    )


@pytest.fixture
def generation_raw(weather_raw):
    return pd.DataFrame(
        {
            S.TIMESTAMP: weather_raw[S.TIMESTAMP],
            S.SITE_ID: SITE["site_id"],
            S.GENERATION_KWH: 7.5 * weather_raw[S.GTI] / 900,
            S.SOURCE: "pvgis",
            S.IS_SIMULATED: True,
        }
    )

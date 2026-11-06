"""[Member 1] Simple PV model for recent "actuals" on simulated sites.

Why: PVGIS stops at 2023, but the deployed system needs the last 7 days of generation every day
(for the TFT history window and for predicted-vs-actual monitoring). Until real inverter data
exists, we estimate it from Open-Meteo's observed tilted irradiance:

    kWh = k * capacity_kw * (GTI / 1000) * (1 + gamma * (T_cell - 25))
    T_cell = T_air + (NOCT - 20) / 800 * GTI

`k` lumps system losses together. It is calibrated against PVGIS over the training period so
recent pseudo-actuals stay on the same scale as the training target. Rows are labelled
source="pv_model", is_simulated=True.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from solarcast import schemas as S
from solarcast.config import params


def _raw_estimate(weather: pd.DataFrame, capacity_kw: float) -> pd.Series:
    cfg = params()["pv_model"]
    gti = weather[S.GTI].clip(lower=0)
    t_cell = weather[S.TEMP] + (cfg["noct_c"] - 20) / 800 * gti
    derate = 1 + cfg["temp_coeff_per_c"] * (t_cell - 25)
    return capacity_kw * gti / 1000 * derate


def calibrate(weather: pd.DataFrame, pvgis: pd.DataFrame, capacity_kw: float) -> float:
    """Least-squares scale k so the PV model matches PVGIS on overlapping daylight hours."""
    m = weather.merge(pvgis[[S.TIMESTAMP, S.GENERATION_KWH]], on=S.TIMESTAMP).dropna()
    est = _raw_estimate(m, capacity_kw)
    day = est > 0
    k = float(np.dot(est[day], m.loc[day, S.GENERATION_KWH]) / np.dot(est[day], est[day]))
    return round(k, 4)


def estimate_generation(weather: pd.DataFrame, site: dict, k: float) -> pd.DataFrame:
    est = (k * _raw_estimate(weather, site["panel_capacity_kw"])).clip(lower=0)
    return pd.DataFrame(
        {
            S.TIMESTAMP: weather[S.TIMESTAMP],
            S.SITE_ID: site["site_id"],
            S.GENERATION_KWH: est.values,
            S.SOURCE: "pv_model",
            S.IS_SIMULATED: True,
        }
    )

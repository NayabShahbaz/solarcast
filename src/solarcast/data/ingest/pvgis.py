"""[Member 1] PVGIS (EU JRC) simulated hourly PV output - training target while real data is missing.

API: https://re.jrc.ec.europa.eu/api/v5_3/seriescalc (pvcalculation=1). Hourly data: 2005-2023 only.
PVGIS timestamps are the middle of the hour in UTC (e.g. 20230101:0630) and P is the hour's mean
power in W, so floor to the hour for start-of-hour and kWh = P / 1000.
"""

from __future__ import annotations

import pandas as pd

from solarcast import schemas as S
from solarcast.config import params
from solarcast.data.ingest._http import SourceError, get_json

PVGIS_MIN_YEAR, PVGIS_MAX_YEAR = 2005, 2023


def fetch_simulated_pv(site: dict, start_year: int, end_year: int) -> pd.DataFrame:
    """Hourly simulated generation [timestamp, site_id, generation_kwh, source, is_simulated]."""
    if not (PVGIS_MIN_YEAR <= start_year <= end_year <= PVGIS_MAX_YEAR):
        raise SourceError(
            f"pvgis: years must be within {PVGIS_MIN_YEAR}-{PVGIS_MAX_YEAR}, "
            f"got {start_year}-{end_year}"
        )
    q = {
        "lat": site["latitude"],
        "lon": site["longitude"],
        "startyear": start_year,
        "endyear": end_year,
        "pvcalculation": 1,
        "peakpower": site["panel_capacity_kw"],
        "loss": site.get("system_loss_pct", 14),
        "angle": site["tilt_deg"],
        "aspect": site["azimuth_deg"] - 180,  # PVGIS: 0 = south, -90 = east
        "outputformat": "json",
    }
    payload = get_json("pvgis", params()["sources"]["pvgis_url"], q)
    try:
        hourly = payload["outputs"]["hourly"]
    except KeyError as e:
        raise SourceError(f"pvgis: unexpected response shape: {list(payload)}") from e

    df = pd.DataFrame(hourly)
    ts = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", utc=True).dt.floor("h")
    return pd.DataFrame(
        {
            S.TIMESTAMP: ts,
            S.SITE_ID: site["site_id"],
            S.GENERATION_KWH: df["P"].astype(float) / 1000.0,
            S.SOURCE: "pvgis",
            S.IS_SIMULATED: True,
        }
    )

"""[Member 1] NASA POWER hourly weather - stored as a CROSS-CHECK source, not a model feature.

API: https://power.larc.nasa.gov/api/temporal/hourly/point (community=RE, time-standard=UTC)
Hourly values are the mean over the hour starting at the timestamp. Fill value is -999.
Used to sanity-check Open-Meteo (e.g. GHI correlation, smog-season bias) in reports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from solarcast import schemas as S
from solarcast.config import params
from solarcast.data.ingest._http import SourceError, get_json

PARAMS = {
    "ALLSKY_SFC_SW_DWN": S.GHI,
    "T2M": S.TEMP,
    "RH2M": S.REL_HUMIDITY,
    "WS10M": S.WIND_SPEED,
}


def fetch_hourly(site: dict, start: str, end: str) -> pd.DataFrame:
    """Hourly NASA POWER weather between two dates (inclusive), one request per year."""
    url = params()["sources"]["nasa_power_url"]
    frames = []
    for year in range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1):
        s = max(pd.Timestamp(start), pd.Timestamp(year=year, month=1, day=1))
        e = min(pd.Timestamp(end), pd.Timestamp(year=year, month=12, day=31))
        q = {
            "parameters": ",".join(PARAMS),
            "community": "RE",
            "latitude": site["latitude"],
            "longitude": site["longitude"],
            "start": s.strftime("%Y%m%d"),
            "end": e.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "UTC",
        }
        payload = get_json("nasa-power", url, q)
        try:
            data = payload["properties"]["parameter"]
        except KeyError as err:
            raise SourceError(f"nasa-power: unexpected response: {str(payload)[:300]}") from err
        df = pd.DataFrame(data)  # index = "YYYYMMDDHH"
        df.index = pd.to_datetime(df.index, format="%Y%m%d%H", utc=True)
        frames.append(df)

    df = pd.concat(frames).rename(columns=PARAMS).replace(-999.0, np.nan)
    df = df.rename_axis(S.TIMESTAMP).reset_index()
    return df[[S.TIMESTAMP, *PARAMS.values()]]

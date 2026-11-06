"""[Member 1] Open-Meteo weather - the model's feature source (history AND next-day forecast).

History : https://archive-api.open-meteo.com/v1/archive
Forecast: https://api.open-meteo.com/v1/forecast

Open-Meteo radiation at time T is the mean over the PRECEDING hour (T-1h..T). We shift every
row back by 1h so `timestamp` is the start of the hour, matching solarcast.schemas.
"""

from __future__ import annotations

import pandas as pd

from solarcast import schemas as S
from solarcast.config import params
from solarcast.data.ingest._http import SourceError, get_json

HOURLY_VARS = {
    "shortwave_radiation": S.GHI,
    "global_tilted_irradiance": S.GTI,
    "temperature_2m": S.TEMP,
    "cloud_cover": S.CLOUD_COVER,
    "relative_humidity_2m": S.REL_HUMIDITY,
    "wind_speed_10m": S.WIND_SPEED,
}


def _base_query(site: dict) -> dict:
    return {
        "latitude": site["latitude"],
        "longitude": site["longitude"],
        "hourly": ",".join(HOURLY_VARS),
        "tilt": site["tilt_deg"],
        "azimuth": site["azimuth_deg"] - 180,  # Open-Meteo: 0 = south, -90 = east
        "wind_speed_unit": "ms",
        "timezone": "GMT",
    }


def _to_frame(payload: dict, source: str) -> pd.DataFrame:
    hourly = payload.get("hourly")
    if not hourly or not hourly.get("time"):
        raise SourceError(f"{source}: response has no hourly data")
    df = pd.DataFrame(hourly).rename(columns=HOURLY_VARS)
    df[S.TIMESTAMP] = pd.to_datetime(df.pop("time"), utc=True) - pd.Timedelta(hours=1)
    return df[[S.TIMESTAMP, *HOURLY_VARS.values()]]


def fetch_history(site: dict, start: str, end: str) -> pd.DataFrame:
    """Observed/reanalysis hourly weather between two dates (inclusive), one request per year."""
    url = params()["sources"]["open_meteo_archive_url"]
    frames = []
    for chunk_start, chunk_end in _year_chunks(start, end):
        q = _base_query(site) | {"start_date": chunk_start, "end_date": chunk_end}
        frames.append(_to_frame(get_json("open-meteo-archive", url, q), "open-meteo-archive"))
    return pd.concat(frames, ignore_index=True)


def fetch_ghi_history(latitude: float, longitude: float, start: str, end: str) -> pd.Series:
    """Hourly GHI (W/m^2) only, start-of-hour UTC. Needs no tilt, so it works for a site whose
    panel angle isn't known yet (used to judge outage days at the real site)."""
    url = params()["sources"]["open_meteo_archive_url"]
    parts = []
    for chunk_start, chunk_end in _year_chunks(start, end):
        q = {"latitude": latitude, "longitude": longitude, "hourly": "shortwave_radiation",
             "timezone": "GMT", "start_date": chunk_start, "end_date": chunk_end}
        hourly = get_json("open-meteo-archive", url, q).get("hourly") or {}
        if not hourly.get("time"):
            raise SourceError("open-meteo-archive: response has no hourly data")
        ts = pd.to_datetime(hourly["time"], utc=True) - pd.Timedelta(hours=1)
        parts.append(pd.Series(hourly["shortwave_radiation"], index=ts, name=S.GHI, dtype=float))
    return pd.concat(parts)


def fetch_forecast(site: dict, past_days: int = 0, forecast_days: int = 2) -> pd.DataFrame:
    """Hourly forecast (optionally with recent past days). Use next_day_window() to cut 24h."""
    url = params()["sources"]["open_meteo_forecast_url"]
    q = _base_query(site) | {"past_days": past_days, "forecast_days": forecast_days}
    return _to_frame(get_json("open-meteo-forecast", url, q), "open-meteo-forecast")


def next_day_window(df: pd.DataFrame, today_local: pd.Timestamp | None = None) -> pd.DataFrame:
    """The 24 hourly rows covering tomorrow in local time (Asia/Karachi), timestamps in UTC."""
    tz = params()["data"]["timezone"]
    today = (today_local or pd.Timestamp.now(tz=tz)).tz_convert(tz).normalize()
    start = (today + pd.Timedelta(days=1)).tz_convert("UTC")
    end = start + pd.Timedelta(hours=24)
    out = df[(df[S.TIMESTAMP] >= start) & (df[S.TIMESTAMP] < end)].reset_index(drop=True)
    if len(out) != 24:
        raise SourceError(f"open-meteo-forecast: expected 24 next-day rows, got {len(out)}")
    return out


def _year_chunks(start: str, end: str) -> list[tuple[str, str]]:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    chunks = []
    while s <= e:
        chunk_end = min(pd.Timestamp(year=s.year, month=12, day=31), e)
        chunks.append((s.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        s = chunk_end + pd.Timedelta(days=1)
    return chunks

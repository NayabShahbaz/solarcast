"""[Member 3] Request/response schemas for the forecasting API."""

from datetime import datetime

from pydantic import BaseModel, Field


class HourlyRecord(BaseModel):
    timestamp: datetime
    generation_kwh: float | None = None
    ghi_wm2: float
    temp_c: float
    cloud_cover_pct: float
    rel_humidity_pct: float | None = None
    wind_speed_ms: float | None = None


class Site(BaseModel):
    site_id: str
    panel_capacity_kw: float = Field(gt=0)


class PredictRequest(BaseModel):
    site: Site
    history: list[HourlyRecord] = Field(min_length=168, description="Last 7 days, hourly")
    future_weather: list[HourlyRecord] = Field(min_length=24, max_length=24)


class HourlyForecast(BaseModel):
    timestamp: datetime
    p10_kwh: float
    p50_kwh: float
    p90_kwh: float


class PredictResponse(BaseModel):
    site_id: str
    model_version: str
    forecasts: list[HourlyForecast]

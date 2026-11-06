"""[Member 3] FastAPI app: /health, /model-info, /predict.

Run locally: uvicorn solarcast.api.main:app --reload
Until the real TFT is ready, /predict returns a TEMPORARY forecast so the dashboard can be built.
"""

from fastapi import FastAPI

from solarcast import __version__
from solarcast.api.schemas import HourlyForecast, PredictRequest, PredictResponse

app = FastAPI(title="SolarCast API", version=__version__)

MODEL_VERSION = "placeholder-0"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/model-info")
def model_info() -> dict:
    return {"model_name": "solarcast-tft", "model_version": MODEL_VERSION}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    # TODO(Member 3): replace with solarcast.models.predict.predict(...) once Member 2 delivers it.
    forecasts = [
        HourlyForecast(timestamp=w.timestamp, p10_kwh=0.0, p50_kwh=0.0, p90_kwh=0.0)
        for w in req.future_weather
    ]
    return PredictResponse(site_id=req.site.site_id, model_version=MODEL_VERSION, forecasts=forecasts)

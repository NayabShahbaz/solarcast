from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from solarcast.api.main import app

client = TestClient(app)


def _rows(start: datetime, n: int) -> list[dict]:
    return [
        {
            "timestamp": (start + timedelta(hours=i)).isoformat(),
            "generation_kwh": 0.0,
            "ghi_wm2": 0.0,
            "temp_c": 20.0,
            "cloud_cover_pct": 0.0,
        }
        for i in range(n)
    ]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_predict_returns_24_hours():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    body = {
        "site": {"site_id": "lahore_pvgis_01", "panel_capacity_kw": 10},
        "history": _rows(t0, 168),
        "future_weather": _rows(t0 + timedelta(hours=168), 24),
    }
    r = client.post("/predict", json=body)
    assert r.status_code == 200
    assert len(r.json()["forecasts"]) == 24


def test_predict_rejects_short_history():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    body = {
        "site": {"site_id": "x", "panel_capacity_kw": 10},
        "history": _rows(t0, 10),
        "future_weather": _rows(t0, 24),
    }
    assert client.post("/predict", json=body).status_code == 422

<!-- Draft for D2 (API, Docker, deployment). Not part of the D1 PDF: D1 excludes APIs, Docker and cloud deployment. -->

# API, CI and deployment plan

## API

A **FastAPI** service (`src/solarcast/api/`) exposes three endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check for the container and the load balancer |
| `GET /model-info` | Name and version of the model being served (`solarcast-tft`) |
| `POST /predict` | Input: site (`site_id`, `panel_capacity_kw`), the last 7 days of hourly history (≥ 168 rows) and 24 hours of forecast weather. Output: 24 hourly rows of `p10_kwh, p50_kwh, p90_kwh`, plus `model_version` |

Pydantic schemas (`api/schemas.py`) reject bad requests before they reach the model, for example
a non-positive capacity or the wrong number of hours. The output columns match the **forecast
log** in the data contract (`timestamp, p10_kwh, p50_kwh, p90_kwh, model_version`), so every
served forecast can later be compared with actual generation by the monitoring code. The API
will load the model from the MLflow registry by alias (`models:/solarcast-tft@production`, set by
`MODEL_ALIAS` in `.env`). Until Member 2's model is promoted, `/predict` returns a placeholder
forecast with the same shape, which lets the dashboard and the tests be built in parallel.

## Continuous integration

`.github/workflows/ci.yml` runs on **every pull request and every push to `main`**:

1. Python 3.11, dependencies installed with `uv` (`.[data,api,dev]`)
2. `ruff check src tests` (lint)
3. `pytest -q` (unit tests for ingestion, preprocessing, validation, monitoring errors and the API)

`main` is protected: changes only enter through a pull request with a green `test` check. Heavy
training libraries (torch) are not installed in CI, so tests that need them use
`pytest.importorskip("torch")` and are skipped there instead of failing. The README shows the CI status badge.

## Deployment plan (D2)

- **Package:** `docker/api.Dockerfile` builds a CPU-only API image; `docker-compose.yml` runs the
  API, the dashboard and Prefect together locally.
- **Deliver:** `.github/workflows/cd.yml` will (1) run an evaluation gate (the new model must beat
  the baseline), (2) build the image tagged with the git SHA, (3) push it to **AWS ECR**, and
  (4) deploy it to **EC2** with `scripts/deploy_ec2.sh`. It is disabled until the AWS secrets are
  added.
- **Roll back:** `scripts/rollback.sh` redeploys the previous image tag and resets the MLflow alias.
- **Observe:** container logs and API latency go to **CloudWatch**; data drift and forecast errors
  come from the Evidently monitoring.

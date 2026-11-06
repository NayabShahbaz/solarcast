# SolarCast

Day-ahead **hourly** solar generation forecasts (kWh) for net-metered rooftop systems in Lahore,
served by a reproducible, automated and monitored ML pipeline: data and experiments on DagsHub,
API on AWS.

**Team (BCS-7A):** 23L-3008 · 23L-1018 · 23L-0565

```
NASA POWER / Open-Meteo / PVGIS / inverter CSV
        │  Prefect (daily)            ── Member 1
        ▼
   raw (DVC) ──► Pandera validate ──► preprocess ──► processed (DVC on DagsHub)
        │
        ▼                              ── Member 2
   windows + features ──► baselines / Chronos-Bolt / TFT ──► MLflow registry
        │  promotion gate
        ▼                              ── Member 3
   GitHub Actions ──► Docker (CPU) ──► ECR ──► EC2 FastAPI ──► CloudWatch
        │
        ▼                              ── Member 1 + 3
   Evidently drift + errors ──► Streamlit dashboard / retraining trigger
```

## Repository layout

```
├── configs/sites.yaml          site coordinates, capacity, simulated vs real
├── params.yaml                 all pipeline/model parameters
├── data/                       raw/ + processed/ via DVC (data/*.dvc); interim/ = daily state
├── src/solarcast/
│   ├── schemas.py              ★ shared data contract (all three review changes)
│   ├── config.py               loads params, sites, .env
│   ├── data/                   M1  ingest/ (open_meteo, pvgis, nasa_power, pv_model, inverter),
│   │                               preprocess, validate (Pandera), storage (DagsHub), pipeline
│   ├── flows/                  M1  Prefect: ingestion, training, retraining, schedules
│   ├── monitoring/             M1  Evidently drift, forecast errors, retrain trigger
│   ├── features/               M2  windows, splits, calendar features
│   ├── models/                 M2  baselines, chronos, tft, train, evaluate, promote, predict
│   ├── api/                    M3  FastAPI /health /model-info /predict
│   └── dashboard/              M3  Streamlit
├── tests/                      pytest (data/, models/, api/)
├── docker/ + docker-compose.yml   M3 images (api, dashboard, pipeline) + local stack
├── infra/aws/  scripts/        M3  AWS notes, deploy + rollback scripts
├── .github/workflows/          M3  ci.yml (tests), cd.yml (ECR/EC2)
├── notebooks/                  exploration only — nothing in production imports these
├── reports/                    monitoring output (local; synced to DagsHub)
└── docs/                       data_contract.md, data_workflow.md
```

> **Data + experiments live on DagsHub:**
> [NayabShahbaz/solarcast](https://dagshub.com/NayabShahbaz/solarcast) holds the DVC remote,
> the daily/monitoring bucket and the MLflow server. AWS is used only for deploying the API
> (ECR, EC2, CloudWatch). Setup: [docs/data_workflow.md](docs/data_workflow.md).

## Setup

Use **Python 3.11** (PyTorch Forecasting / Prefect / Evidently are safest there), and install
with **uv**. Plain pip backtracks for 10+ minutes on this dependency set.

```bash
py -3.11 -m venv .venv             # macOS/Linux: python3.11 -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install uv
uv pip install -e ".[data,api,dev]"      # everyone; then add your component:
uv pip install -e ".[train]"             # Member 2
uv pip install -e ".[dashboard]"         # Member 3
copy .env.example .env             # macOS/Linux: cp ; fill in DagsHub user + token
dvc pull                           # once the DagsHub remote is configured
pytest
```

Data pipeline commands: [docs/data_workflow.md](docs/data_workflow.md).

Local stack (Prefect :4200, API :8000, dashboard :8501). MLflow is the shared DagsHub server
from `.env`; a local MLflow (:5000) runs only with `--profile offline`:
```bash
docker compose up --build
```

## Team workflow
- `main` is protected: no direct pushes, PR + 1 review + green CI.
- Branch names: `m1/ingestion-flow`, `m2/tft-baseline`, `m3/fastapi-skeleton`.
- Changes to `schemas.py`, `models/predict.py` or `api/schemas.py` need review from every affected member.
- Never commit data, model files or `.env` — data goes through DVC (DagsHub), models through MLflow (DagsHub).

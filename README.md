# SolarCast

Day-ahead **hourly** solar generation forecasts (kWh) for net-metered rooftop systems in Lahore,
served by a reproducible, automated and monitored ML pipeline on AWS.

**Team (BCS-7A):** 23L-3008 · 23L-1018 · 23L-0565

```
NASA POWER / Open-Meteo / PVGIS / inverter CSV
        │  Prefect (daily)            ── Member 1
        ▼
   S3 raw ──► Pandera validate ──► preprocess ──► S3 processed (DVC)
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
├── data/                       DVC-tracked, NOT in git (raw/ interim/ processed/ reference/)
├── src/solarcast/
│   ├── schemas.py              ★ shared data contract (all three review changes)
│   ├── config.py               loads params, sites, .env
│   ├── data/                   M1  ingest/ (nasa_power, open_meteo, pvgis, inverter),
│   │                               preprocess, validate (Pandera), storage (S3)
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
├── reports/                    monitoring output (local; synced to S3)
└── docs/                       data_contract.md, data_workflow.md
```

## Setup

Use **Python 3.11** (PyTorch Forecasting / Prefect / Evidently are safest there).

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"            # then add your component:
pip install -e ".[data]"           # Member 1
pip install -e ".[train]"          # Member 2
pip install -e ".[api,dashboard]"  # Member 3
cp .env.example .env               # fill in AWS / MLflow settings
dvc pull                           # once the S3 remote is configured
pytest
```

Local stack (MLflow :5000, Prefect :4200, API :8000, dashboard :8501):
```bash
docker compose up --build
```

## Team workflow
- `main` is protected: no direct pushes, PR + 1 review + green CI.
- Branch names: `m1/ingestion-flow`, `m2/tft-baseline`, `m3/fastapi-skeleton`.
- Changes to `schemas.py`, `models/predict.py` or `api/schemas.py` need review from every affected member.
- Never commit data, model files or `.env` — data goes through DVC/S3, models through MLflow.

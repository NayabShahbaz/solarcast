# SolarCast

![CI](https://github.com/NayabShahbaz/solarcast/actions/workflows/ci.yml/badge.svg)

**Links:** [GitHub](https://github.com/NayabShahbaz/solarcast) ·
[DagsHub (data + DVC)](https://dagshub.com/NayabShahbaz/solarcast) ·
[MLflow experiments](https://dagshub.com/NayabShahbaz/solarcast.mlflow)

Day-ahead **hourly** solar generation forecasts (kWh) for net-metered rooftop systems in Lahore,
built as a reproducible, tested and monitored ML pipeline. Data versions (DVC) and experiments
(MLflow) live on DagsHub; the FastAPI service is packaged with Docker (AWS deployment planned for D2).

**Team (BCS-7A):**

| Member | Name | Roll no. | Owns |
|---|---|---|---|
| 1 | Nayab Shahbaz | 23L-3008 | Data ingestion, Pandera validation, DVC + DagsHub, Prefect flows, Evidently monitoring |
| 2 | Samiha Hamid | 23L-1018 | Features, baselines + TFT models, evaluation, MLflow tracking + model registry |
| 3 | Izza Fatima | 23L-0565 | FastAPI service, CI (GitHub Actions), Docker/deployment, dashboard, README + report |

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
   GitHub Actions CI ──► Docker (CPU) FastAPI  (D2: ──► ECR ──► EC2 ──► CloudWatch)
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
> (ECR, EC2, CloudWatch; planned for D2). Setup: [docs/data_workflow.md](docs/data_workflow.md).

## Reproduce from a fresh clone

Needs Python 3.11 and a DagsHub account (free) with read access to the repo.

```bash
git clone https://github.com/NayabShahbaz/solarcast.git && cd solarcast
py -3.11 -m venv .venv && .venv\Scripts\activate      # macOS/Linux: python3.11 -m venv .venv && source .venv/bin/activate
pip install uv && uv pip install -e ".[data,api,dev,train]"
copy .env.example .env                                 # macOS/Linux: cp; then set DAGSHUB_USER + DAGSHUB_TOKEN
python scripts/configure_dvc_remote.py                 # writes your DagsHub token to .dvc/config.local (git-ignored)
dvc pull                                               # versioned data (tag data-v1) from DagsHub
dvc repro                                              # validate -> train baselines + TFT -> evaluate
```

`dvc repro` logs every training run to [MLflow on DagsHub](https://dagshub.com/NayabShahbaz/solarcast.mlflow);
the main model is registered as `solarcast-tft`.

## Development setup (per member)

Use **Python 3.11** (PyTorch Forecasting / Prefect / Evidently are safest there), and install
with **uv**. Plain pip backtracks for 10+ minutes on this dependency set.

```bash
py -3.11 -m venv .venv             # macOS/Linux: python3.11 -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install uv
uv pip install -e ".[data,api,dev]"      # everyone; then add your component:
uv pip install -e ".[train]"             # Member 2
uv pip install -e ".[dashboard]"         # Member 3
copy .env.example .env             # macOS/Linux: cp ; set DAGSHUB_USER + DAGSHUB_TOKEN
python scripts/configure_dvc_remote.py   # DagsHub DVC credentials (token stays local)
dvc pull                           # versioned data from DagsHub
pytest
```

## Reproduce the pipeline

The batch pipeline is defined in [`dvc.yaml`](dvc.yaml) as named stages:

```
ingest -> preprocess -> validate -> train_baseline, train_tft -> evaluate
```

```bash
dvc repro            # run every stage whose code, params or inputs changed
dvc repro --force    # rebuild the full pipeline from scratch (re-downloads source data)
dvc dag              # show the stage graph
dvc metrics show     # validation and evaluation metrics
dvc push             # share outputs via DagsHub, then commit dvc.lock
```

`validate` exits non-zero on any failed data check, so no model is trained on bad data.
All parameters live in [`params.yaml`](params.yaml). Experiments are tracked on
[DagsHub MLflow](https://dagshub.com/NayabShahbaz/solarcast.mlflow).
Data details: [docs/data_workflow.md](docs/data_workflow.md) and
[docs/data_contract.md](docs/data_contract.md).

Local stack (Prefect :4200, API :8000, dashboard :8501). MLflow is the shared DagsHub server
from `.env`; a local MLflow (:5000) runs only with `--profile offline`:
```bash
docker compose up --build
```

## Team workflow
- `main` is protected: no direct pushes. Changes go through a PR with green CI (`test`).
- Each member works on their own branch and opens PRs into `main`: `nayab-space` (Member 1),
  `izza-space` (Member 3); Member 2 picks theirs.
- Changes to `schemas.py`, `models/predict.py` or `api/schemas.py` need review from every affected member.
- Never commit data, model files or `.env` — data goes through DVC (DagsHub), models through MLflow (DagsHub).

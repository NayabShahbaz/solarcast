# Data workflow (Member 1)

Everything here is run from the repo root with the virtual environment active.
Data decisions and column rules: [data_contract.md](data_contract.md).

## 1. Environment (once per machine)

The project needs **Python 3.11** (3.13 is too new for PyTorch Forecasting / Evidently).

```bash
py -3.11 -m venv .venv                     # Windows; macOS/Linux: python3.11 -m venv .venv
.venv\Scripts\activate                     # macOS/Linux: source .venv/bin/activate
pip install uv                             # plain pip backtracks for 10+ minutes on this stack
uv pip install -e ".[data,api,dev]"        # Member 2 adds ,train ; Member 3 adds ,dashboard
copy .env.example .env                     # macOS/Linux: cp ; then fill in DagsHub values
pytest
```

## 2. Where data lives

| What | Path | Versioned by |
|---|---|---|
| Historical API pulls (PVGIS, Open-Meteo, NASA POWER) | `data/raw/<source>/` | **DVC** (`data/raw.dvc`) |
| Training dataset + `metadata.json` | `data/processed/` | **DVC** (`data/processed.dvc`) |
| Daily state: recent actuals, forecast inputs, daily pulls | `data/interim/` | object storage (S3 API) |
| Monitoring output for the dashboard | `reports/monitoring/` | object storage (S3 API) |

Storage is **DagsHub** for now and **AWS S3** later. Only `.env` / `.dvc/config` change:
[planning/aws_migration.md](../planning/aws_migration.md).

## 3. Get the exact dataset someone else used

```bash
git checkout <commit-or-tag>      # e.g. data-v1, or the dataset_version logged in MLflow
dvc pull
```

## 4. Run the pipeline

| Command | What it does | When |
|---|---|---|
| `python -m solarcast.flows.ingestion_flow --mode history` | PVGIS + Open-Meteo (+ NASA cross-check) → clean → Pandera → `data/processed/hourly.parquet` | once, or when sites/dates change |
| `python -m solarcast.flows.ingestion_flow --mode daily` | last ~8 days of weather + pseudo-actuals → `data/interim/recent/`; tomorrow's 24 h inputs → `data/interim/forecast_inputs/` | daily, 20:00 PKT |
| `python -m solarcast.flows.retraining_flow` | Evidently drift + forecast errors → `reports/monitoring/latest.json` → retrain if triggered | daily, 20:30 PKT |
| `python -m solarcast.flows.retraining_flow --demo-drift` | same, with a controlled smog-like shift: shows drift → retraining | demo |
| `python -m solarcast.flows.training_flow` | Member 2's train + evaluate on the current dataset version | on demand / triggered |
| `python -m solarcast.flows.schedules` | serves the two daily deployments (needs `prefect server start`) | on the server |

**The single workflow command** (completion check): `ingestion_flow --mode history` gets,
validates and produces the dataset. `retraining_flow --force` then runs training on it.

Each flow starts a temporary local Prefect server if `PREFECT_API_URL` is not set. To see runs
in the UI, run `prefect server start`, open http://127.0.0.1:4200 and set
`PREFECT_API_URL=http://127.0.0.1:4200/api` in `.env`.

## 5. After rebuilding the dataset: version it

```bash
dvc add data/raw data/processed
git add data/raw.dvc data/processed.dvc
git commit -m "data: rebuild processed dataset (<what changed>)"
dvc push
git tag data-v<N> && git push --tags
```

`metadata.json` records row counts, date range, the `pv_model` scale factor `k` and the NASA
cross-check. Mention big changes in the commit message.

## 6. How retraining is triggered

`monitoring/errors.should_retrain` returns `{"retrain", "reasons", "notes"}`:

- **Data drift:** Evidently drift share > `drift_share_threshold` (0.5) for
  `drift_consecutive_runs` (3) **consecutive daily runs**. One unusual week is not enough.
  The reference is the *same season* in 2020–2022, daylight hours only.
- **Forecast error:** daylight MAE > `mae_threshold_kwh`. This stays off until the first
  production model sets a baseline.
- **Cooldown:** no automatic retrain within `retrain_cooldown_days` (7) of the last one.
  `--force` overrides it.
- **The trigger only starts training.** Member 2's evaluation and the promotion gate decide
  whether the new model is deployed.

Until Member 2's `train()` exists, a triggered run logs `training.status = "pending_member2"`
and still completes.

## 7. Diagnosing a failed run

| Where it failed | What you see | Usual cause → fix |
|---|---|---|
| `ingest-*` task | `SourceError: <source>: HTTP 4xx/5xx …` | API down or bad parameters. Tasks retry twice; rerun later. PVGIS years must be 2005–2023 |
| `validate-and-build-processed` | `Pandera validation failed:` then one line per check, with row counts | Bad upstream values. Open the raw parquet for that source and check the named column |
| `ingest-daily-*` | `expected 24 next-day rows, got N` | Forecast API returned a short horizon; rerun |
| `ingest-daily-*` | `metadata.json missing` | Run the history build or `dvc pull` first |
| `drift-report` | `hourly.parquet missing` | `dvc pull` |
| training subflow | `TrainingNotAvailable` | Expected until Member 2's code lands |

Prefect keeps every run's logs. With a Prefect server running, open the flow run in the UI.
Without one, the console output is the log.

## 8. DagsHub setup (one time, Member 1 — pending)

1. Create the DagsHub repo connected to the GitHub repo, then create a token
   (User settings → Tokens). Put the user name and token in `.env`.
2. Copy the exact commands from the DagsHub repo page → **Remote → DVC → S3 (boto)**. They look like:
   ```bash
   dvc remote add -d origin s3://dvc
   dvc remote modify origin endpointurl https://dagshub.com/<dagshub-user>/solarcast.s3
   dvc remote modify --local origin access_key_id <dagshub-token>
   dvc remote modify --local origin secret_access_key <dagshub-token>
   git add .dvc/config && git commit -m "Configure DVC remote (DagsHub)"
   dvc push
   ```
   `--local` keeps the token in `.dvc/config.local`, which git ignores.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` runs for ages | Use `uv pip install` (step 1) |
| `dvc pull` → 403 / AccessDenied | Token missing from `.dvc/config.local`, or no access to the DagsHub repo |
| `storage not configured - kept … local only` | Expected until `.env` has real DagsHub values |
| `NoCredentialsError` from storage | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` missing in `.env` |
| Uploads go to real AWS by mistake | `S3_ENDPOINT_URL` is empty in `.env` |

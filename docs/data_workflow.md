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
| Historical API pulls (PVGIS, Open-Meteo, NASA POWER) | `data/raw/<source>/` | **DVC**: `ingest` stage output |
| Training dataset + `metadata.json` | `data/processed/` | **DVC**: `preprocess` stage output |
| Validation report | `reports/validation.json` | **DVC metrics** (in git) |
| Daily state: recent actuals, forecast inputs, daily pulls | `data/interim/` | DagsHub bucket `daily/` |
| Monitoring output for the dashboard | `reports/monitoring/` | DagsHub bucket `monitoring/` |
| Experiments and models | — | DagsHub MLflow (Member 2) |

Everything remote lives in **one DagsHub repo**,
[NayabShahbaz/solarcast](https://dagshub.com/NayabShahbaz/solarcast), connected to the GitHub repo.

### Looking at the data

The files are parquet (binary), so open them with the peek script rather than a text editor:

```bash
python scripts/peek_data.py                         # every data file with its row/column count
python scripts/peek_data.py data/raw/open_meteo     # columns, types, date range, daytime sample
python scripts/peek_data.py data/raw --csv          # export to data/interim/preview/*.csv (git-ignored, opens in Excel)
```

Raw files are stored *after* parsing: the API JSON is already turned into our column names
(`schemas.py`) with UTC start-of-hour timestamps, but no cleaning has been applied yet.
On the web, DagsHub shows the DVC-tracked `data/` folder in the repo's file browser.

## 3. Get the exact dataset someone else used

```bash
git checkout <commit-or-tag>      # e.g. data-v1, or the dataset_version logged in MLflow
dvc pull
```

## 4. Run the pipeline

### Reproducible batch pipeline (`dvc.yaml`)

```bash
dvc repro            # ingest -> preprocess -> validate -> train_baseline, train_tft -> evaluate
dvc repro validate   # just the data stages (Member 1)
dvc dag              # draw the pipeline
dvc metrics show     # validation.json + eval.json
```

| Stage | Command | Output |
|---|---|---|
| `ingest` | `python -m solarcast.data.stages ingest` | `data/raw/` |
| `preprocess` | `python -m solarcast.data.stages preprocess` | `data/processed/` |
| `validate` | `python -m solarcast.data.stages validate` | `reports/validation.json`; **non-zero exit stops the pipeline** |
| `train_baseline`, `train_tft` | `python -m solarcast.models.train --model …` (Member 2) | `models/<model>/` + MLflow runs |
| `evaluate` | `python -m solarcast.models.evaluate` (Member 2) | `reports/eval.json` |

Activate the venv first, because stages call `python`. DVC reruns a stage only when its code,
params (`params.yaml`) or inputs change. `dvc repro --force` rebuilds everything from scratch.

### Prefect flows (scheduling, retries, retraining)

| Command | What it does | When |
|---|---|---|
| `python -m solarcast.flows.ingestion_flow --mode history` | runs `dvc repro validate` under Prefect | once, or when sites/dates change |
| `python -m solarcast.flows.ingestion_flow --mode daily` | last ~8 days of weather + pseudo-actuals → `data/interim/recent/`; tomorrow's 24 h inputs → `data/interim/forecast_inputs/` | daily, 20:00 PKT |
| `python -m solarcast.flows.retraining_flow` | Evidently drift + forecast errors → `reports/monitoring/latest.json` → retrain if triggered | daily, 20:30 PKT |
| `python -m solarcast.flows.retraining_flow --demo-drift` | same, with a controlled smog-like shift: shows drift → retraining | demo |
| `python -m solarcast.flows.training_flow [--force]` | runs `dvc repro evaluate` (training stages); `--force` retrains even if nothing changed | on demand / triggered |
| `python -m solarcast.flows.schedules` | serves the two daily deployments (needs `prefect server start`) | on the server |

**The single workflow command** (completion check): `dvc repro` gets, validates and produces
the dataset, then runs training on it.

Each flow starts a temporary local Prefect server if `PREFECT_API_URL` is not set. To see runs
in the UI, run `prefect server start`, open http://127.0.0.1:4200 and set
`PREFECT_API_URL=http://127.0.0.1:4200/api` in `.env`.

## 5. After rebuilding the dataset: version it

```bash
dvc repro validate                    # or the full `dvc repro`
git add dvc.lock reports/validation.json
git commit -m "data: rebuild processed dataset (<what changed>)"
dvc push
git tag data-v<N> && git push --tags
```

`dvc.lock` records the exact hash of every stage's inputs and outputs. Checking out a commit
and running `dvc pull` restores that exact data.

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

## 8. DagsHub access (once per member)

1. **Repo owner (Member 1):** add the member on DagsHub: repo → **Settings → Collaborators**
   (write access, so they can `dvc push` and log MLflow runs).
2. **The member:** create a DagsHub account (sign in with GitHub), then go to
   **User settings → Tokens** and create a token.
3. In `.env`, set `DAGSHUB_USER` and `DAGSHUB_TOKEN` to **your own** values. Keep
   `DAGSHUB_REPO_OWNER=NayabShahbaz` and `DAGSHUB_REPO=solarcast`.
4. Run:
   ```bash
   python scripts/configure_dvc_remote.py   # writes your token to .dvc/config.local (git-ignored)
   dvc pull
   ```

The DVC remote uses DagsHub's S3-compatible endpoint (`s3://dvc` at
`https://dagshub.com/NayabShahbaz/solarcast.s3`). That's only the protocol: no AWS account is involved.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` runs for ages | Use `uv pip install` (step 1) |
| `dvc pull`/`push` → 403 / AccessDenied | Rerun `scripts/configure_dvc_remote.py`. If it persists, you're not a collaborator on the DagsHub repo yet |
| `storage not configured - kept … local only` | `.env` still has `<placeholders>` in the `DAGSHUB_*` lines |
| Token leaked or expired | Create a new token on DagsHub, update `DAGSHUB_TOKEN` in `.env`, rerun the configure script |

# Repository and reproducibility

**Repository.** The code is on GitHub
([NayabShahbaz/solarcast](https://github.com/NayabShahbaz/solarcast)) in a standard layout:
`src/solarcast/` (data, features, models), `tests/`, `configs/`, `params.yaml`, `dvc.yaml` and
`docs/`. The README gives the project description, setup steps, how to run the pipeline and the
folder structure. All parameters live in `params.yaml`, so a run is defined by code + params + data
version, never by hand-edited scripts.

**No data or weights in Git.** `.gitignore` excludes `models/*`, `mlruns/`, `data/interim/`,
`.venv/` and secrets (`.env`). Raw and processed data are DVC stage outputs stored on the DagsHub
remote: Git holds only `dvc.lock` (the hashes), and the dataset is tagged `data-v1`. Model files
are DVC outputs as well, and every run's metrics and model go to MLflow on DagsHub. Credentials
stay in a local `.env` and `.dvc/config.local`, which are never committed.

**Team workflow.** `main` is protected: every change goes through a pull request from a member's
own branch, so all three members' work appears as their own commits. As an extra check, GitHub
Actions (`ci.yml`) runs `ruff` and `pytest` on every pull request (tests for ingestion parsing,
preprocessing, validation and stage wiring), and a pull request can only be merged when it passes.
The README's CI badge shows the status of `main`.

**Reproduce from scratch** in four commands (once per machine: put a DagsHub token in `.env` and
run `python scripts/configure_dvc_remote.py`; full steps in the README):

```bash
git clone https://github.com/NayabShahbaz/solarcast.git && cd solarcast
uv pip install -e ".[data,api,dev,train]"
dvc pull
dvc repro
```

`dvc repro` runs the named stages `ingest → preprocess → validate → train_baseline, train_tft →
evaluate`; `validate` stops the pipeline on bad data, so no model is trained on it.

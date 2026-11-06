# D1: what's left, and who does it

Status as of **2026-11-06**. Tick items off in a PR as they're done.

Links for the PDF:
- GitHub: https://github.com/NayabShahbaz/solarcast
- DagsHub (data + MLflow): https://dagshub.com/NayabShahbaz/solarcast
- MLflow UI: https://dagshub.com/NayabShahbaz/solarcast.mlflow

## D1 requirements at a glance

| # | Requirement (from the D1 brief) | Status | Owner |
|---|---|---|---|
| 1 | Clean repo + README | Structure done; final README pass needed | **Member 3** |
| 2 | All members have commits | Only Member 1 so far | **Members 2 + 3** |
| 3 | No raw data or weights committed | ✅ data via DVC, `.env` ignored. Models must go through DVC/MLflow too | everyone |
| 4 | Ingest + DVC with DagsHub remote | ✅ done (`dvc pull` works, tag `data-v1`) | Member 1 |
| 5 | Validation before training, re-runnable | ✅ `validate` stage fails `dvc repro` on bad data | Member 1 |
| 6 | Baseline + main model evaluated | ❌ `train.py`, `evaluate.py` are stubs | **Member 2** |
| 7 | MLflow on DagsHub, model registered in **Staging/Production** | ❌ no runs yet | **Member 2** |
| 8 | `dvc.yaml` named stages; `dvc repro` rebuilds everything from scratch | ⚠️ data stages ✅; stops at `train_baseline` until #6 is done | Member 2 (then re-check: Member 1) |
| 9 | PDF, 3–4 pages: links, screenshots (≥ 2 MLflow runs, registered model in Staging, `dvc dag`), write-up | ⚠️ `dvc dag` + Member 1's section done | **Member 3** compiles |
| 10 | CI green on `main` | ✅ today; must stay green after every merge | **Member 3** |

---

## Member 1 (Nayab): almost done

Done: data pipeline, Pandera validation, `dvc.yaml` data stages, DagsHub DVC remote, `data-v1`,
Prefect flows, Evidently monitoring, real rooftop test data, write-up
([nayab_part.md](nayab_part.md)), `dvc dag` figure ([dvc_dag.png](dvc_dag.png)).

Left:
- [ ] **Add both teammates** with write access. Nothing below can start without this:
  - GitHub: repo → Settings → Collaborators → Add people
  - DagsHub: repo → Settings → Collaborators (write)
- [ ] Put their GitHub usernames in `.github/CODEOWNERS` and uncomment the lines.
- [ ] Merge the open `nayab-space` PR.
- [ ] After Member 2 lands training: run `dvc repro` in a **fresh clone** once more to prove the
      full pipeline runs from scratch.
- [ ] (Not needed for D1) Real site: panel kW, tilt and expansion date in `configs/sites.yaml`.

---

## Member 2: models + MLflow (most of the remaining work)

### Setup (once)
1. Accept the GitHub and DagsHub invitations.
2. Clone, create a branch (e.g. `member2-models`), then:
   ```bash
   py -3.11 -m venv .venv && .venv\Scripts\activate
   pip install uv && uv pip install -e ".[data,api,dev,train]"
   copy .env.example .env          # set DAGSHUB_USER + DAGSHUB_TOKEN (your own token)
   python scripts/configure_dvc_remote.py
   dvc pull                        # data-v1 dataset
   pytest
   ```

### Work
- [ ] **`src/solarcast/models/train.py`** (stages `train_baseline`, `train_tft` in `dvc.yaml`):
  - read `data/processed/hourly.parquet` (already validated)
  - chronological split from `params.yaml → split` (train 2020–22, val 2023 H1, test 2023 H2)
  - **target per kW**: `generation_kwh / panel_capacity_kw` ([data contract](../data_contract.md#target-per-kw-agreed-2026-11-06))
  - log params, metrics and artifacts to **DagsHub MLflow** (URI and credentials come from `.env`)
  - log the dataset version: `dataset_version = data-v1`
  - write `models/<model>/` plus `run.json` = `{"run_id", "model", "dataset_version"}`
  - `--model baselines` and `--model tft` → **at least 2 MLflow runs** (the brief needs ≥ 2)
- [ ] **`src/solarcast/models/evaluate.py`**: score every `models/*/run.json` on the TEST split
  (MAE/RMSE in kWh, daylight hours) and write `reports/eval.json`. **Baseline and main model
  both evaluated.**
- [ ] **Register** the main model as `solarcast-tft` and move it to **Staging**
  (`promote.py`: `transition_model_version_stage(..., "Staging")`, plus an alias).
- [ ] Run the **full `dvc repro`**: it must get through `train_baseline`, `train_tft` and `evaluate`.
  Then `git add dvc.lock reports/eval.json`, `dvc push` (model files), and a PR.
- [ ] **Screenshots** for the PDF, saved in `docs/report/`:
  - `mlflow_runs.png`: experiment page showing ≥ 2 runs with metrics
  - `mlflow_registry_staging.png`: `solarcast-tft` with a version in **Staging**
- [ ] Write-up **`docs/report/member2_part.md`** (~¾ page): baselines, main model, metrics
  table, why the main model was chosen.
- [ ] Optional: accuracy on the real roof (`data/real`, `usable` hours only), reported separately.

Don't commit `models/` or any weights to Git: DVC tracks `models/*` as stage outputs.

---

## Member 3: PDF compilation, README, CI green

### Setup + commits (D1 needs commits from every member)
- [ ] Accept the invitations, clone, branch (e.g. `member3-api`), install `.[data,api,dev,dashboard]`.
- [ ] Make your own commits through PRs. The README pass, CI badge and PDF sources below count,
  and so does the API skeleton work.
- [ ] Confirm the **forecast log columns** in [data_contract.md](../data_contract.md)
  (`timestamp, p10_kwh, p50_kwh, p90_kwh, model_version`).

### 1. PDF compilation (3–4 pages)
Sources, all in `docs/report/`:

| Section | Source | From |
|---|---|---|
| Title, team, links (GitHub, DagsHub, MLflow) | top of this file | — |
| Problem + architecture (½ page) | README intro + diagram | Member 3 |
| Data pipeline, validation, DVC | [nayab_part.md](nayab_part.md) | Member 1 ✅ |
| `dvc dag` figure | [dvc_dag.png](dvc_dag.png) | Member 1 ✅ |
| Models + evaluation + MLflow | `member2_part.md` | Member 2 |
| Screenshots: ≥ 2 MLflow runs, model in Staging | `mlflow_runs.png`, `mlflow_registry_staging.png` | Member 2 |
| Deployment plan / API + CI (¼–½ page) | `member3_part.md` | Member 3 |
| Reproduce in 4 commands (`git clone`, `uv pip install`, `dvc pull`, `dvc repro`) | README | Member 3 |

Steps:
- [ ] Collect the sections into one document (Google Docs/Word). Keep each member's text, but
  trim it to fit **3–4 pages total**. Figures can be small: they must be readable, not big.
- [ ] Number the figures (Figure 1, 2, …) and replace the "Figure X" placeholders.
- [ ] Check every link opens **without being logged in**. If the repos are private, add the
  instructor as a collaborator or make them public before submitting.
- [ ] Export as PDF and commit it as `docs/report/D1_report.pdf` (or submit it, if the course
  says not to commit it).

### 2. README final pass
- [ ] Team line: names next to roll numbers, plus who owns what (Member 1/2/3 areas).
- [ ] Links at the top: GitHub, DagsHub, MLflow.
- [ ] "Reproduce" section works copy-paste on a **fresh clone**:
  `uv pip install -e ".[data,api,dev,train]"`, `.env` setup, `python scripts/configure_dvc_remote.py`,
  `dvc pull`, `dvc repro`.
- [ ] Mention the registered model (`solarcast-tft`, Staging) once Member 2 has it.
- [ ] Add the CI badge:
  `![CI](https://github.com/NayabShahbaz/solarcast/actions/workflows/ci.yml/badge.svg)`
- [ ] Remove anything that's out of date (placeholders, "TODO", AWS bits that no longer apply
  to data/MLflow).

### 3. CI green on `main`
What CI runs (`.github/workflows/ci.yml`, on every push and PR): Python 3.11, `uv pip install -e
".[data,api,dev]"`, `ruff check src tests`, `pytest -q`.

- [ ] Every PR needs a green **`test`** check before merging (`main` is protected).
- [ ] After the last D1 merge, open **Actions** and confirm the latest run on `main` is ✅.
- [ ] If it's red:
  - **ruff** errors → run `ruff check --fix src tests` locally, commit
  - **pytest** fails → run `pytest -q` locally and fix the test or the code (don't delete tests)
  - **install** fails (e.g. new library) → add it to the right group in `pyproject.toml`.
    The CI installs `data,api,dev` only, so tests must not import `train`-only libraries
    (torch etc.) at the top level. Use `pytest.importorskip("torch")` in those tests.
- [ ] Member 2's training code imports torch/lightning: make sure its tests are skipped on CI
  (above) or that CI installs `.[train]` too. Agree which before merging their PR.

---

## Order (dependencies)

```
Member 1: add collaborators ──► Member 2: setup ──► train + evaluate + registry ──► screenshots ─┐
                            └─► Member 3: setup ──► README pass + CI badge ─────────────────────┤
                                                                                                ▼
                         Member 1: fresh-clone `dvc repro` check ──► Member 3: compile PDF ──► submit
```

**Done when:** `main` has commits from all three; CI is green; a fresh clone runs `dvc pull` and
`dvc repro` end to end; MLflow shows ≥ 2 runs and `solarcast-tft` in Staging; and the PDF
(3–4 pages, links + 3 screenshots + write-up) is submitted.

# Data pipeline, validation and versioning (Member 1: Nayab Shahbaz)

**Links:**
- GitHub: https://github.com/NayabShahbaz/solarcast
- DagsHub (DVC data + MLflow): https://dagshub.com/NayabShahbaz/solarcast
- MLflow server: https://dagshub.com/NayabShahbaz/solarcast.mlflow

## 1. Data sources

SolarCast predicts hourly rooftop-solar generation (kWh) for the next day in Lahore. There is no
public metered data for Lahore homes, so the training target is **simulated**. A real PV-model
simulation is used, not random numbers.

| Role | Source | What we take | Why |
|---|---|---|---|
| Target | **PVGIS** (EU JRC, API v5.3) | Hourly PV output for a 10 kW system (tilt 20°, south-facing, 14 % losses) | Physically modelled from satellite irradiance; free and documented |
| Features | **Open-Meteo** (archive + forecast API) | GHI, tilted irradiance (GTI), temperature, cloud cover, humidity, wind | The same provider serves history *and* the next-day forecast, so training and prediction inputs match |
| Cross-check | **NASA POWER** | GHI, temperature, humidity, wind | An independent satellite source, used only to sanity-check Open-Meteo |

All training data comes from one reference system (10 kW, 20° tilt, south-facing). The model
predicts output **per kW**, and the API multiplies by each user's system size. This works for any
system size, but assumes a roughly south-facing roof. Other orientations are a stated limitation.

The training dataset covers 2020-01-01 to 2023-12-31 (PVGIS only provides years up to 2023).
The split is set in `params.yaml`: train 2020–2022, validation 2023 H1, test 2023 H2.

The cross-check agrees well. Open-Meteo and NASA POWER GHI correlate at **0.946** over **17,857**
daylight hours, with a mean bias of **−8.9 W/m²**.

For dates after 2023 (daily runs and monitoring), PVGIS has no data. There, `pv_model.py` makes
pseudo-actuals from the observed weather. It uses a simple irradiance–temperature PV model and
scales it by a factor **k = 0.9225**, fitted so that it matches PVGIS over the training years.

## 2. Preprocessing

The three APIs report their hours differently, so each one is shifted to **UTC start-of-hour**:

- PVGIS stamps hours as `HH:30`, so its times are rounded down.
- Open-Meteo labels the *end* of each hour, so its times are shifted back 1 hour. One extra day
  is fetched so the last hour is not lost.
- NASA POWER already uses start-of-hour, so it is unchanged.

Cleaning rules (`preprocess.py`):

- Gaps of up to 3 hours are interpolated and marked `is_imputed = True`. Longer gaps are dropped.
- Physically impossible values are rejected (for example cloud cover outside 0–100 %).
- If GHI is below 5 W/m² (night), generation is set to 0.
- Generation is limited to 1.1 × panel capacity.

The result is one table, `data/processed/hourly.parquet`. It has **35,064 rows** (every hour of
4 years), **13 columns** and **0 nulls**. The column names and units are fixed in `schemas.py`,
which all three members share.

## 3. Validation before training

Validation is a separate pipeline stage that runs **before any model is trained**. A
**Pandera** schema checks:

- column types, value ranges and that nothing is null;
- that timestamps are UTC and on the hour;
- that there are no duplicate (site, hour) rows;
- that generation is never above capacity × margin;
- that generation is zero at night;
- that `is_simulated` matches the data source.

All checks run together, so a single report lists every problem.

The stage writes `reports/validation.json` (rows, nulls, imputed rows, failed checks). DVC
tracks this file as a metric. If any check fails, the stage exits non-zero and `dvc repro` stops
before training. A unit test (`tests/data/test_stages.py`) puts a bad value into the data on
purpose and confirms that the pipeline stops. Current result: **0 failed checks, 0 imputed
rows**.

### Real rooftop data (test set)

To check the model on a real roof, we added Member 1's home system: a SolarMax 3.5 kW hybrid
inverter with no grid feed-in. Its monitoring portal exports were cleaned into **509 days** of
daily totals (Jun 2025 to Nov 2026) and **2,446 hours** of hourly data, of which **2,229 hours
are usable** for testing. Several checks went into this:

- The portal's hourly figures turned out to be in **China time (UTC+8)** and about **9 % low**.
  We found both by comparing them with the 5-minute readings, and corrected them.
- **17 outage days** (system or Wi-Fi offline) are flagged and left out.
- Because the battery can fill up with nowhere to send power, **held-back hours** (battery
  full, inverter limiting solar) are detected from the 5-minute data and excluded.
- The raw exports contain the device serial number and account name, so only the cleaned data
  is versioned. The raw files never leave the owner's machine.

## 4. Reproducible pipeline (DVC + DagsHub)

The pipeline is declared in `dvc.yaml` as named stages (Figure X, `dvc dag`):

```
ingest -> preprocess -> validate -> train_baseline, train_tft -> evaluate
```

Each stage lists its exact code files, its parameters from `params.yaml`, its inputs and its
outputs. DVC re-runs a stage only when one of these changes. `dvc.lock` records the hash of
every input and output, so each Git commit points to one exact version of the dataset.

The data is stored in the **DagsHub** DVC remote (DagsHub's S3-compatible storage). Raw data and
the processed dataset are never committed to Git: Git only holds `dvc.lock` and the small
metrics files. Any teammate can get the exact data with `git checkout <commit>` and `dvc pull`.

**Reproducibility check:** we made a fresh clone with no data and ran `dvc repro validate`. It
downloaded all three sources again, rebuilt the dataset and validated it in about 2 minutes. The
rebuilt dataset was **identical** to the original, row for row.

Line endings are fixed to LF (`.gitattributes`, `.editorconfig`). Without this, Windows and
Linux machines would see different file hashes for the same code.

## 5. Orchestration and monitoring (Prefect + Evidently)

**Prefect** flows wrap the pipeline and add retries, logging and schedules:

- `ingestion_flow --mode history` runs the DVC data stages.
- `ingestion_flow --mode daily` (20:00 PKT) fetches the last 8 days of weather and
  pseudo-actuals, plus the next day's 24-hour forecast inputs for the API. These go to the
  DagsHub bucket.
- `retraining_flow` (20:30 PKT) runs **Evidently** drift reports. The current window is compared
  with the same season in the training years (±14 days, daylight hours only), so normal changes
  between seasons do not count as drift.

Retraining is triggered only if drift lasts for **3 consecutive daily runs**, with a **7-day
cooldown** between retrains. A trigger only starts training. Member 2's evaluation and promotion
gate decide whether the new model is deployed.

## 6. Problems faced

- **Different hour conventions** between the APIs. Without the shifts in Section 2, the data
  would be misaligned by an hour and the dataset would be missing its last hour.
- **False drift alarms.** Comparing against the whole year flagged normal seasonal weather as
  drift. Comparing against the same season, and requiring the drift to persist, fixed this.
- **Hashes differing between machines** because of CRLF vs LF line endings. Fixed by
  standardising on LF.

---

### Figures for the PDF (in this folder)
- `dvc_dag.png`: output of `dvc dag` (pipeline stages). Caption: *"Figure X: DVC pipeline
  stages (`dvc dag`). `validate` must pass before either training stage runs."*
- `dvc_dag.md`: the same graph as a Mermaid flowchart, if a drawn diagram is preferred.
- Optional: a screenshot of the DagsHub repo page showing the DVC-tracked `data/` folder.

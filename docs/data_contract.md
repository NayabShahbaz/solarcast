# Data contract (Members 1 + 2) — DRAFT, confirm with Member 2

Source of truth in code: [`src/solarcast/schemas.py`](../src/solarcast/schemas.py), enforced by
[`src/solarcast/data/validate.py`](../src/solarcast/data/validate.py) (Pandera).
Processed file: `data/processed/hourly.parquet` (DVC-tracked), with `metadata.json` next to it.

## Decisions (agreed 2026-11-06)

| Decision | Choice | Why |
|---|---|---|
| Generation target | **PVGIS simulated** (2020–2023) until real inverter exports exist | PVGIS hourly data stops at 2023 |
| Feature weather | **Open-Meteo** (archive for history, forecast API for next day) | Same source in training and serving, so no train/serve skew |
| NASA POWER | Ingested as a **cross-check** only (`metadata.json → crosscheck`) | Proposal source; sanity-checks Open-Meteo irradiance |
| Recent actuals (2024+) | **`pv_model`**: PV model on Open-Meteo tilted irradiance, scaled to PVGIS | Deployed system needs 7 days of generation history every day |
| Splits | train 2020–2022, val 2023 H1, test 2023 H2 (`params.yaml → split`) | Chronological, no leakage |
| System size | **Model works per kW** (see below) | Training data is one 10 kW system; users have other sizes |

## Target per kW (agreed 2026-11-06)

The training data comes from **one reference system**: 10 kW, tilt 20°, facing south
(azimuth 180°), 14 % losses (`configs/sites.yaml`). So that one model serves any system size:

- **Member 2 (training):** predict `generation_kwh / panel_capacity_kw`, i.e. kWh per kW
  (between 0 and 1.1). Lag/history features made from `generation_kwh` are divided by capacity the
  same way. The processed file stays in kWh. Divide while building the windows, in one place.
- **Member 2 (`predict.py`):** multiply the per-kW forecast (p10/p50/p90) by the request's
  `panel_capacity_kw` before returning it.
- **Member 3 (API):** `/predict` already requires `panel_capacity_kw`. Responses stay in kWh.
- **Evaluation:** report metrics in kWh for the 10 kW reference site, and also per kW
  (MAE ÷ 10), so results compare across sizes.

**Limitation (state in the report):** generation scales with size, but **not** with tilt or
orientation. Forecasts assume a roughly south-facing roof at a typical tilt (`gti_wm2` is also
computed for 20° south). East/west or flat roofs will have a different daily curve. Covering
those would need more simulated systems plus tilt/azimuth columns (a schema change).

## Columns

| Column              | Type          | Unit | Rule                                                          |
|---------------------|---------------|------|---------------------------------------------------------------|
| `timestamp`         | datetime, UTC | —    | **start** of the hour; unique per `site_id`                   |
| `site_id`           | str           | —    | from `configs/sites.yaml`                                     |
| `source`            | str           | —    | `pvgis`, `pv_model` or `inverter`                             |
| `is_simulated`      | bool          | —    | False only for `inverter`; report simulated vs real separately |
| `generation_kwh`    | float         | kWh  | 0 ≤ x ≤ 1.1 × capacity; **0 when GHI < 5 W/m²**              |
| `ghi_wm2`           | float         | W/m² | 0–1400, mean over the hour                                    |
| `gti_wm2`           | float         | W/m² | 0–1500, tilted (panel-plane) irradiance, mean over the hour   |
| `temp_c`            | float         | °C   | −10 to 55                                                     |
| `cloud_cover_pct`   | float         | %    | 0–100                                                         |
| `rel_humidity_pct`  | float         | %    | 0–100                                                         |
| `wind_speed_ms`     | float         | m/s  | 0–60, at 10 m                                                 |
| `panel_capacity_kw` | float         | kW   | > 0, constant per site                                        |
| `is_imputed`        | bool          | —    | True if any value in the row was interpolated                 |

## Timestamp alignment (the subtle part)

| Source     | Raw timestamp meaning               | Conversion to `timestamp`  |
|------------|-------------------------------------|----------------------------|
| PVGIS      | middle of the hour (`HH:30`), UTC   | floor to the hour          |
| Open-Meteo | end of the averaging hour, UTC      | subtract 1 hour            |
| NASA POWER | start of the hour, UTC              | none                       |

## Missing and invalid data

1. Duplicate hours: keep the last.
2. Out-of-range values become missing. Tiny negative rounding noise is clipped to 0.
3. Gaps of **≤ 3 h** (`max_gap_hours_interpolate`) are linearly interpolated and set `is_imputed=True`.
4. Longer gaps: the rows are **dropped**. **Member 2:** windows must not cross a missing hour.
   Check that timestamps in a 168 + 24 h window are contiguous.

## Files other members read

| File | Producer | Consumer |
|---|---|---|
| `data/processed/hourly.parquet` | ingestion (history) | Member 2 training |
| `data/interim/recent/<site_id>.parquet` | ingestion (daily) | API history window (Member 3), monitoring |
| `data/interim/forecast_inputs/<site_id>_<date>.parquet` | ingestion (daily) | API `/predict` future weather (Member 3) |
| `data/interim/forecasts/<site_id>_<date>.parquet` | daily prediction / API (Member 3) | error monitoring (Member 1) |
| `reports/monitoring/latest.json`, `history.jsonl`, `drift_<site>.html` | monitoring | dashboard (Member 3) |

Forecast log columns (**Member 3 to confirm**): `timestamp, p10_kwh, p50_kwh, p90_kwh, model_version`.

## Real site: `lahore_home_01` (test data only)

Member 1's rooftop: SolarMax SOLON DUAL 3.8 kW hybrid inverter (6 kW MPPT input), "Solar of Things" portal, **no grid
feed-in**. Used to **test** the model on a real roof. It is never part of the training set.

| File (DVC: `data/real.dvc`) | Rows | Notes |
|---|---|---|
| `data/real/lahore_home_01/hourly.parquet` | one per UTC start-of-hour | where hourly detail exists: Jun 2025 (2 weeks), 8 Aug 2026 onwards |
| `data/real/lahore_home_01/daily.parquet` | one per portal day | every day since install (16 Jun 2025) |
| `data/real/lahore_home_01/summary.json` | — | coverage, outage days, flags, settings still missing |

Built by `python -m solarcast.data.real` on the owner's machine. The raw exports (in
`data/inverter/`, git-ignored) contain the serial number and portal user name, so they are
**never pushed**. The cleaned files contain no identifiers. Teammates get them with `dvc pull`.

Hourly columns: the shared `timestamp, site_id, source="inverter", is_simulated=False,
generation_kwh, panel_capacity_kw` plus:

| Column | Meaning |
|---|---|
| `hourly_from` | `5min` (mean of 5-minute readings) or `hourly_export` (portal hourly column, rescaled) |
| `is_scaled` | export hour rescaled so the day's daylight hours add up to the reported daily total |
| `is_partial` | the day has fewer than 24 hours (install day, today, export gaps) |
| `is_outage` | the day produced < 15 % of what its sunshine normally gives (NA: no weather yet) |
| `held_back` | battery full and not charging for most of the hour, so the inverter limited solar (NA: no 5-minute data) |
| `usable` | complete day AND not an outage AND not held back: **only these hours count toward accuracy** |

**Evidence behind the rules** (checked on the real exports, 2026-11-06):

- **Portal hourly columns are China time (UTC+8).** Against the 5-minute data they correlate
  0.987 as UTC+8 and worse with a 1-hour shift either way. Daily dates use the same calendar;
  the day boundary falls at 21:00 PKT, at night, so it doesn't split any solar production.
- **Daily totals are trustworthy, the hourly columns read ~9 % low.** Daily totals equal the
  integrated 5-minute readings (ratio 1.000, correlation 0.9998 over 38 days). The hourly
  columns add up to ~0.91 of that, so they are rescaled (median factor 1.105).
- **Night noise.** Readings show 0.01–0.08 kW at night (up to ~90 V on the longer string after
  the expansion). Night is decided by sun elevation (and voltage for 5-minute data) and set to 0.
  Reported daily totals still include this noise (~0.2–0.3 kWh/day).
- **Panel expansion in August 2025** (owner confirmed; first day at the new level: 11 Aug). Daily kWh jumps from ≤ 20 to ~30, and the midday PV
  voltage from ~218 V to ~390 V. Panel kW before and after: **pending from the owner**
  (`capacity_history` in `configs/sites.yaml`). Until then `panel_capacity_kw` is empty and the
  capacity check is skipped.
- **Direction: south (azimuth 180°).** On clear October days production is centred at 11:52,
  against a solar noon of 11:48. **Tilt: pending from the owner.**

**Member 2:** compare forecasts with `hourly.parquet` where `usable` is True, and report the
real-site metrics separately from the simulated ones. Use per-kW values once `panel_capacity_kw`
is filled in. Daily accuracy can use `daily.parquet` (excluding `is_outage` and `is_partial`).

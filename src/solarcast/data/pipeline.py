"""[Member 1] Plain-Python pipeline steps. Prefect flows in solarcast.flows wrap these as tasks,
so every step can also be run and tested without Prefect.

Files produced:
  data/raw/<source>/<site_id>_<start>_<end>.parquet     historical API pulls       -> DVC
  data/processed/hourly.parquet                          training dataset           -> DVC
  data/processed/metadata.json                           summary, pv_model k, params -> DVC
  data/interim/raw_daily/<site_id>_<date>.parquet        daily API pull             -> DagsHub daily/
  data/interim/recent/<site_id>.parquet                  rolling weather + actuals  -> DagsHub daily/
  data/interim/forecast_inputs/<site_id>_<date>.parquet  next-day inputs for the API -> DagsHub daily/
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from solarcast import schemas as S
from solarcast.config import INTERIM_DIR, PROCESSED_DIR, RAW_DIR, params, sites
from solarcast.data import preprocess, storage, validate
from solarcast.data.ingest import nasa_power, open_meteo, pv_model, pvgis
from solarcast.data.ingest._http import SourceError

log = logging.getLogger(__name__)

PROCESSED_FILE = PROCESSED_DIR / "hourly.parquet"
METADATA_FILE = PROCESSED_DIR / "metadata.json"
RECENT_DIR = INTERIM_DIR / "recent"
FORECAST_DIR = INTERIM_DIR / "forecast_inputs"


def _save(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    log.info("wrote %s (%d rows)", path, len(df))
    return path


def simulated_sites() -> list[dict]:
    return [s for s in sites() if s.get("is_simulated", True)]


# --------------------------------------------------------------------------- historical build
def ingest_history(site: dict, start: str | None = None, end: str | None = None,
                   include_crosscheck: bool = True) -> dict[str, Path]:
    """Download raw history for one site: PVGIS target, Open-Meteo features, NASA cross-check."""
    p = params()["data"]
    start, end = start or p["start_date"], end or p["end_date"]
    tag = f"{site['site_id']}_{start}_{end}"
    paths = {
        "pvgis": _save(
            pvgis.fetch_simulated_pv(site, pd.Timestamp(start).year, pd.Timestamp(end).year),
            RAW_DIR / "pvgis" / f"{tag}.parquet",
        ),
        # +1 day: Open-Meteo rows are shifted back 1h, so the last hour comes from the next day
        "open_meteo": _save(
            open_meteo.fetch_history(
                site, start, (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            ),
            RAW_DIR / "open_meteo" / f"{tag}.parquet",
        ),
    }
    if include_crosscheck:
        try:
            paths["nasa_power"] = _save(
                nasa_power.fetch_hourly(site, start, end), RAW_DIR / "nasa_power" / f"{tag}.parquet"
            )
        except (SourceError, KeyError, ValueError) as e:  # cross-check only: never block on it
            log.warning("NASA POWER cross-check skipped: %s", e)
    return paths


def raw_paths(site: dict, start: str | None = None, end: str | None = None) -> dict[str, Path]:
    """Paths ingest_history() writes for a site, for the sources that exist on disk."""
    p = params()["data"]
    tag = f"{site['site_id']}_{start or p['start_date']}_{end or p['end_date']}"
    paths = {src: RAW_DIR / src / f"{tag}.parquet" for src in ("pvgis", "open_meteo", "nasa_power")}
    missing = [s for s in ("pvgis", "open_meteo") if not paths[s].exists()]
    if missing:
        raise FileNotFoundError(f"raw data missing for {site['site_id']}: {missing} - run ingest")
    return {k: v for k, v in paths.items() if v.exists()}


def build_processed(raw: dict[str, dict[str, Path]]) -> tuple[pd.DataFrame, dict]:
    """raw = {site_id: paths from ingest_history}. Returns (dataset, metadata).

    Not validated here: validation is its own DVC stage (solarcast.data.stages validate), so a
    bad dataset stops `dvc repro` before any training stage runs.
    """
    frames, k_by_site = [], {}
    for site in simulated_sites():
        paths = raw[site["site_id"]]
        weather = pd.read_parquet(paths["open_meteo"])
        gen = pd.read_parquet(paths["pvgis"])
        frames.append(preprocess.build_site_dataset(weather, gen, site))
        k_by_site[site["site_id"]] = pv_model.calibrate(
            preprocess.clean_weather(weather), gen, site["panel_capacity_kw"]
        )

    df = pd.concat(frames, ignore_index=True)
    meta = {
        "summary": preprocess.summarise(df),
        "pv_model_k": k_by_site,
        "data_params": params()["data"],
        "crosscheck": crosscheck_report(raw),
    }
    return df, meta


def crosscheck_report(raw: dict[str, dict[str, Path]]) -> dict:
    """Correlation and mean bias of Open-Meteo vs NASA POWER GHI (daylight hours)."""
    out = {}
    for site_id, paths in raw.items():
        if "nasa_power" not in paths:
            continue
        om = pd.read_parquet(paths["open_meteo"])[[S.TIMESTAMP, S.GHI]]
        nasa = pd.read_parquet(paths["nasa_power"])[[S.TIMESTAMP, S.GHI]]
        m = om.merge(nasa, on=S.TIMESTAMP, suffixes=("_om", "_nasa")).dropna()
        m = m[(m[f"{S.GHI}_om"] > 5) | (m[f"{S.GHI}_nasa"] > 5)]
        if m.empty:
            continue
        out[site_id] = {
            "ghi_corr": round(float(m[f"{S.GHI}_om"].corr(m[f"{S.GHI}_nasa"])), 3),
            "ghi_mean_bias_wm2": round(float((m[f"{S.GHI}_om"] - m[f"{S.GHI}_nasa"]).mean()), 1),
            "hours": len(m),
        }
    return out


def save_processed(df: pd.DataFrame, meta: dict) -> Path:
    _save(df, PROCESSED_FILE)
    # No build timestamp and LF line endings: the same data must give the same DVC hash on
    # every machine, otherwise each rebuild would look like a new dataset version.
    METADATA_FILE.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    # Not uploaded to the bucket: the processed dataset is a DVC stage output (dvc repro + push).
    return PROCESSED_FILE


def load_metadata() -> dict:
    if not METADATA_FILE.exists():
        raise FileNotFoundError(
            f"{METADATA_FILE} missing - run the historical build first "
            "(python -m solarcast.flows.ingestion_flow --mode history) or `dvc pull`"
        )
    return json.loads(METADATA_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- daily ingestion
def ingest_daily(site: dict, today_local: pd.Timestamp | None = None,
                 past_days: int = 8) -> dict[str, Path]:
    """Daily run: recent weather + pseudo-actuals (rolling file) and tomorrow's forecast inputs.

    Uses Open-Meteo's forecast endpoint with past_days, which returns recent analysed weather
    for the past days and the forecast for the coming days in one consistent series.
    """
    tz = params()["data"]["timezone"]
    today = (today_local or pd.Timestamp.now(tz=tz)).tz_convert(tz).normalize()
    raw = open_meteo.fetch_forecast(site, past_days=past_days, forecast_days=2)
    stamp = today.strftime("%Y-%m-%d")
    raw_path = _save(raw, INTERIM_DIR / "raw_daily" / f"{site['site_id']}_{stamp}.parquet")

    weather = preprocess.clean_weather(raw)
    cutoff = today.tz_convert("UTC")  # hours before local midnight today are "observed"
    observed = weather[weather[S.TIMESTAMP] < cutoff]
    forecast = open_meteo.next_day_window(weather, today)
    validate.validate_weather_input(forecast, expected_rows=params()["window"]["horizon_hours"])

    k = load_metadata()["pv_model_k"][site["site_id"]]
    gen = pv_model.estimate_generation(observed, site, k)
    recent = preprocess.align_weather_and_generation(
        observed, preprocess.clean_generation(gen, site["panel_capacity_kw"]), site
    )
    recent = validate.validate_processed(recent)

    recent_path = RECENT_DIR / f"{site['site_id']}.parquet"
    if recent_path.exists():
        recent = pd.concat([pd.read_parquet(recent_path), recent])
        recent = recent.drop_duplicates([S.SITE_ID, S.TIMESTAMP], keep="last")
        recent = recent.sort_values(S.TIMESTAMP).reset_index(drop=True)
    paths = {
        "recent": _save(recent, recent_path),
        "forecast_inputs": _save(forecast, FORECAST_DIR / f"{site['site_id']}_{stamp}.parquet"),
    }
    for p in (raw_path, *paths.values()):
        storage.maybe_upload(p, storage.key("daily", f"{p.parent.name}/{p.name}"))
    return paths

"""[Member 1] ingestion -> validation -> preprocessing, as a Prefect flow.

Two modes:
  history  one-off/occasional: PVGIS + Open-Meteo (+ NASA cross-check) -> data/processed/hourly.parquet
  daily    scheduled: recent weather + pseudo-actuals, and tomorrow's forecast inputs for the API

Run locally:
  python -m solarcast.flows.ingestion_flow --mode history
  python -m solarcast.flows.ingestion_flow --mode daily
"""

from __future__ import annotations

import argparse

from prefect import flow, get_run_logger, task

from solarcast.data import pipeline, validate


@task(retries=2, retry_delay_seconds=60, task_run_name="ingest-history-{site[site_id]}")
def ingest_history(site: dict, start: str | None, end: str | None) -> dict:
    return pipeline.ingest_history(site, start, end)


@task(task_run_name="validate-and-build-processed")
def build_processed(raw: dict) -> tuple:
    logger = get_run_logger()
    try:
        return pipeline.build_processed(raw)
    except Exception as e:
        if type(e).__name__ == "SchemaErrors":
            logger.error("Pandera validation failed:\n%s", validate.failure_summary(e))
        raise


@task(task_run_name="save-processed")
def save_processed(df, meta: dict) -> str:
    return str(pipeline.save_processed(df, meta))


@task(retries=2, retry_delay_seconds=120, task_run_name="ingest-daily-{site[site_id]}")
def ingest_daily(site: dict) -> dict:
    return {k: str(v) for k, v in pipeline.ingest_daily(site).items()}


@flow(name="solarcast-ingestion", log_prints=True)
def ingestion_flow(mode: str = "daily", start: str | None = None, end: str | None = None) -> dict:
    logger = get_run_logger()
    sites = pipeline.simulated_sites()
    if mode == "history":
        raw = {s["site_id"]: ingest_history(s, start, end) for s in sites}
        df, meta = build_processed(raw)
        path = save_processed(df, meta)
        logger.info("processed dataset: %s | %s", path, meta["summary"])
        logger.info("pv_model k: %s | NASA cross-check: %s", meta["pv_model_k"], meta["crosscheck"])
        logger.info("next: `dvc add data/processed/hourly.parquet` and commit the .dvc file")
        return {"processed": path, "summary": meta["summary"]}
    if mode == "daily":
        out = {s["site_id"]: ingest_daily(s) for s in sites}
        logger.info("daily ingestion done: %s", out)
        return out
    raise ValueError(f"unknown mode {mode!r} (use 'history' or 'daily')")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["history", "daily"], default="daily")
    ap.add_argument("--start")
    ap.add_argument("--end")
    a = ap.parse_args()
    ingestion_flow(mode=a.mode, start=a.start, end=a.end)

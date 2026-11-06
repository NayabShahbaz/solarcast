"""[Member 1] Data ingestion as a Prefect flow.

Two modes:
  history  `dvc repro validate`: the ingest -> preprocess -> validate stages of dvc.yaml
           (PVGIS + Open-Meteo + NASA cross-check -> data/processed -> Pandera checks)
  daily    scheduled: recent weather + pseudo-actuals, and tomorrow's forecast inputs for the API

Run locally:
  python -m solarcast.flows.ingestion_flow --mode history [--force]
  python -m solarcast.flows.ingestion_flow --mode daily
"""

from __future__ import annotations

import argparse
import json

from prefect import flow, get_run_logger, task

from solarcast.data import pipeline
from solarcast.data.stages import VALIDATION_REPORT
from solarcast.flows import _dvc


@task(retries=1, retry_delay_seconds=120, task_run_name="dvc-repro-data")
def repro_data(force: bool) -> str:
    args = ["repro", "validate", *(["--force"] if force else [])]
    return _dvc.run(*args)


@task(retries=2, retry_delay_seconds=120, task_run_name="ingest-daily-{site[site_id]}")
def ingest_daily(site: dict) -> dict:
    return {k: str(v) for k, v in pipeline.ingest_daily(site).items()}


@flow(name="solarcast-ingestion", log_prints=True)
def ingestion_flow(mode: str = "daily", force: bool = False) -> dict:
    logger = get_run_logger()
    if mode == "history":
        try:
            out = repro_data(force)
        except _dvc.DvcError:
            if VALIDATION_REPORT.exists():
                report = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
                if not report.get("valid", True):
                    logger.error("Pandera validation failed:\n%s", "\n".join(report["failures"]))
            raise
        logger.info("dvc repro:\n%s", out.strip())
        meta = pipeline.load_metadata()
        logger.info("processed dataset %s: %s", _dvc.dataset_version(), meta["summary"])
        logger.info("next: commit dvc.lock and run `dvc push`")
        return {"dataset_version": _dvc.dataset_version(), "summary": meta["summary"]}
    if mode == "daily":
        out = {s["site_id"]: ingest_daily(s) for s in pipeline.simulated_sites()}
        logger.info("daily ingestion done: %s", out)
        return out
    raise ValueError(f"unknown mode {mode!r} (use 'history' or 'daily')")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["history", "daily"], default="daily")
    ap.add_argument("--force", action="store_true", help="history: rerun stages even if cached")
    a = ap.parse_args()
    ingestion_flow(mode=a.mode, force=a.force)

"""[Member 1] DVC stage entry points - one command per data stage in dvc.yaml.

    python -m solarcast.data.stages ingest       # APIs -> data/raw/
    python -m solarcast.data.stages preprocess   # data/raw/ -> data/processed/
    python -m solarcast.data.stages validate     # Pandera checks -> reports/validation.json

Normally run through `dvc repro`, which only reruns stages whose code, params or inputs changed.
`validate` exits non-zero on any failed check, so `dvc repro` stops before training.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from solarcast import schemas as S
from solarcast.config import REPORTS_DIR
from solarcast.data import pipeline, validate

log = logging.getLogger("solarcast.stages")

VALIDATION_REPORT = REPORTS_DIR / "validation.json"


def ingest() -> None:
    for site in pipeline.simulated_sites():
        paths = pipeline.ingest_history(site)
        log.info("ingested %s: %s", site["site_id"], {k: str(v) for k, v in paths.items()})


def preprocess() -> None:
    raw = {s["site_id"]: pipeline.raw_paths(s) for s in pipeline.simulated_sites()}
    df, meta = pipeline.build_processed(raw)
    pipeline.save_processed(df, meta)
    log.info("processed: %s", meta["summary"])
    log.info("pv_model k: %s | NASA cross-check: %s", meta["pv_model_k"], meta["crosscheck"])


def run_validation() -> int:
    df = pd.read_parquet(pipeline.PROCESSED_FILE)
    report = {
        "rows": len(df),
        "columns": len(df.columns),
        "sites": int(df[S.SITE_ID].nunique()),
        "null_cells": int(df.isna().sum().sum()),
        "imputed_rows": int(df[S.IS_IMPUTED].sum()),
        "failed_checks": 0,
        "failures": [],
    }
    try:
        validate.validate_processed(df)
        report["valid"] = True
    except Exception as e:
        if type(e).__name__ != "SchemaErrors":
            raise
        report["valid"] = False
        report["failures"] = validate.failure_summary(e).splitlines()
        report["failed_checks"] = len(report["failures"])

    VALIDATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["valid"]:
        log.error("validation FAILED (%d checks):\n%s", report["failed_checks"],
                  "\n".join(report["failures"]))
        return 1
    log.info("validation passed: %d rows, %d columns, %d nulls",
             report["rows"], report["columns"], report["null_cells"])
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m solarcast.data.stages")
    ap.add_argument("stage", choices=["ingest", "preprocess", "validate"])
    stage = ap.parse_args(argv).stage
    if stage == "ingest":
        ingest()
    elif stage == "preprocess":
        preprocess()
    else:
        return run_validation()
    return 0


if __name__ == "__main__":
    sys.exit(main())

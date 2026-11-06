"""Loads params.yaml, configs/sites.yaml and .env into one place. Shared by everyone."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
INVERTER_DIR = DATA_DIR / "inverter"  # raw real-site exports: owner's machine only, never pushed
REAL_DIR = DATA_DIR / "real"  # cleaned real-site data, identifiers removed (versioned: dvc add)
REPORTS_DIR = ROOT / "reports"
MODELS_DIR = ROOT / "models"

load_dotenv(ROOT / ".env")


@lru_cache
def params() -> dict:
    with open(ROOT / "params.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def sites() -> list[dict]:
    with open(ROOT / "configs" / "sites.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sites"]


def env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)

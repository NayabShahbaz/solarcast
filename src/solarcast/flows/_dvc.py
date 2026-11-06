"""Run DVC from Prefect flows. dvc.yaml is the single definition of the batch pipeline; the
flows only orchestrate it (schedules, retries, retrain triggers)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from solarcast.config import ROOT

_BIN = Path(sys.executable).parent  # .venv/Scripts (Windows) or .venv/bin


class DvcError(RuntimeError):
    def __init__(self, args: list[str], output: str):
        self.output = output
        tail = "\n".join(output.strip().splitlines()[-15:])
        super().__init__(f"dvc {' '.join(args)} failed:\n{tail}")


def run(*args: str) -> str:
    """Run `dvc <args>` in the repo root and return its combined output; raise DvcError."""
    env = os.environ | {"PATH": f"{_BIN}{os.pathsep}{os.environ.get('PATH', '')}",
                        "PYTHONIOENCODING": "utf-8"}
    exe = _BIN / ("dvc.exe" if os.name == "nt" else "dvc")
    proc = subprocess.run([str(exe), *args], check=False, cwd=ROOT, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise DvcError(list(args), out)
    return out


def dataset_version() -> str | None:
    """Content hash of data/processed recorded in dvc.lock - identifies the exact training data."""
    lock = ROOT / "dvc.lock"
    if not lock.exists():
        return None
    stages = yaml.safe_load(lock.read_text(encoding="utf-8")).get("stages", {})
    for out in stages.get("preprocess", {}).get("outs", []):
        if out.get("path") == "data/processed":
            return out.get("md5")
    return None

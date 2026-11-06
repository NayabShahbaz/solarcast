"""Thin adapter around Evidently (>= 0.7 API) so its version changes stay in one file.

Evidently picks a drift test per column (K-S p-value for small samples, Wasserstein distance for
large ones). For p-value methods drift means value < threshold; for distances, value >= threshold.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset

_VALUE_DRIFT = re.compile(r"ValueDrift\(column=(?P<col>[^,]+),method=(?P<method>[^,]+),"
                          r"threshold=(?P<thr>[^)]+)\)")


def data_drift(reference: pd.DataFrame, current: pd.DataFrame, html_path: Path) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        snapshot = Report([DataDriftPreset()]).run(current_data=current, reference_data=reference)
    snapshot.save_html(str(html_path))
    snapshot.save_json(str(html_path.with_suffix(".json")))
    return parse(snapshot.dict())


def parse(result: dict) -> dict:
    share, columns = 0.0, {}
    for m in result["metrics"]:
        name, value = m["metric_name"], m["value"]
        if name.startswith("DriftedColumnsCount"):
            share = float(value["share"])
        elif match := _VALUE_DRIFT.match(name):
            thr, method = float(match["thr"]), match["method"]
            drifted = value < thr if "p_value" in method else value >= thr
            columns[match["col"]] = {
                "method": method,
                "score": round(float(value), 6),
                "threshold": thr,
                "drifted": bool(drifted),
            }
    return {
        "drift_share": round(share, 3),
        "drifted_columns": sorted(c for c, v in columns.items() if v["drifted"]),
        "columns": columns,
    }


if __name__ == "__main__":  # debug helper: python -m solarcast.monitoring._evidently <json>
    import sys

    print(json.dumps(parse(json.loads(Path(sys.argv[1]).read_text())), indent=2))

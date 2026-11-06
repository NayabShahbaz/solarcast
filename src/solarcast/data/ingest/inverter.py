"""[Member 1] Real inverter CSV exports (Huawei FusionSolar / Growatt) - NOT IMPLEMENTED YET.

Waiting on a real export: vendor formats differ (column names, energy vs power, local time),
so the parser is written against an actual file, not a guess.
Drop raw exports in data/raw/inverter/<site_id>/ and never edit them by hand.

Output must match the PVGIS ingester: [timestamp (UTC, start of hour), site_id,
generation_kwh, source="inverter", is_simulated=False].
"""

from pathlib import Path

import pandas as pd


def load_inverter_csv(path: Path, site_id: str, vendor: str) -> pd.DataFrame:
    raise NotImplementedError(
        "Inverter parser not written yet - add a sample export to data/raw/inverter/ first"
    )

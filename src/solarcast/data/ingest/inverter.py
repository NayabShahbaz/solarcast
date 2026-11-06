"""[Member 1] Real inverter CSV exports (Huawei FusionSolar / Growatt).

Drop raw exports in data/raw/inverter/<site_id>/ and never edit them by hand.
"""

from pathlib import Path

import pandas as pd


def load_inverter_csv(path: Path, site_id: str, vendor: str) -> pd.DataFrame:
    """Parse a vendor export into [timestamp, site_id, generation_kwh] (is_simulated=False)."""
    raise NotImplementedError

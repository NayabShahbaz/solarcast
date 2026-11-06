"""[Member 1] PVGIS (EU JRC) simulated hourly PV output - fallback when real data is limited.

API: https://re.jrc.ec.europa.eu/api/  (seriescalc endpoint, pvcalculation=1)
Implement this EARLY - it unblocks Member 2 before real inverter data exists.
"""

import pandas as pd


def fetch_simulated_pv(site: dict, start_year: int, end_year: int) -> pd.DataFrame:
    """Return hourly simulated generation for a site from configs/sites.yaml (is_simulated=True)."""
    raise NotImplementedError

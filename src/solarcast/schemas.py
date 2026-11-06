"""DATA CONTRACT shared by Members 1, 2 and 3 (integration point: processed dataset -> training).

Stdlib only so every component can import it. Pandera enforcement lives in data/validate.py.
Changing a column here = a PR reviewed by all three members. DRAFT - confirm with Member 2.
"""

# Index / identity
TIMESTAMP = "timestamp"  # tz-aware UTC, hourly, start-of-hour
SITE_ID = "site_id"
SOURCE = "source"  # "pvgis" | "inverter"
IS_SIMULATED = "is_simulated"  # True for PVGIS - report simulated vs real separately

# Target
GENERATION_KWH = "generation_kwh"  # energy produced during the hour

# Weather (observed for history, forecast for the next 24h)
GHI = "ghi_wm2"  # global horizontal irradiance, W/m^2
TEMP = "temp_c"  # 2m air temperature, deg C
CLOUD_COVER = "cloud_cover_pct"  # 0-100
REL_HUMIDITY = "rel_humidity_pct"  # 0-100
WIND_SPEED = "wind_speed_ms"  # m/s

# Static site metadata
PANEL_CAPACITY_KW = "panel_capacity_kw"

WEATHER_COLUMNS = [GHI, TEMP, CLOUD_COVER, REL_HUMIDITY, WIND_SPEED]
PROCESSED_COLUMNS = [
    TIMESTAMP,
    SITE_ID,
    SOURCE,
    IS_SIMULATED,
    GENERATION_KWH,
    *WEATHER_COLUMNS,
    PANEL_CAPACITY_KW,
]

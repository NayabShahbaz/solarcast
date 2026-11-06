"""DATA CONTRACT shared by Members 1, 2 and 3 (integration point: processed dataset -> training).

Stdlib only so every component can import it. Pandera enforcement lives in data/validate.py.
Changing a column here = a PR reviewed by all three members. DRAFT - confirm with Member 2.

Timestamp convention: `timestamp` is the START of the hour in UTC. A row for 06:00 UTC holds
the energy produced and the mean irradiance between 06:00 and 07:00 UTC.
"""

# Index / identity
TIMESTAMP = "timestamp"  # tz-aware UTC, hourly, start-of-hour
SITE_ID = "site_id"
SOURCE = "source"  # "pvgis" | "pv_model" | "inverter"
IS_SIMULATED = "is_simulated"  # True for pvgis/pv_model - report simulated vs real separately

# Target
GENERATION_KWH = "generation_kwh"  # energy produced during the hour

# Weather features - from Open-Meteo (archive for history, forecast for the next 24h)
GHI = "ghi_wm2"  # global horizontal irradiance, W/m^2 (hour mean)
GTI = "gti_wm2"  # global tilted irradiance on the panel plane, W/m^2 (hour mean)
TEMP = "temp_c"  # 2m air temperature, deg C
CLOUD_COVER = "cloud_cover_pct"  # 0-100
REL_HUMIDITY = "rel_humidity_pct"  # 0-100
WIND_SPEED = "wind_speed_ms"  # 10m wind, m/s

# Static site metadata
PANEL_CAPACITY_KW = "panel_capacity_kw"

# Data quality
IS_IMPUTED = "is_imputed"  # True if any value in the row was interpolated

SOURCES = ("pvgis", "pv_model", "inverter")
WEATHER_COLUMNS = [GHI, GTI, TEMP, CLOUD_COVER, REL_HUMIDITY, WIND_SPEED]
PROCESSED_COLUMNS = [
    TIMESTAMP,
    SITE_ID,
    SOURCE,
    IS_SIMULATED,
    GENERATION_KWH,
    *WEATHER_COLUMNS,
    PANEL_CAPACITY_KW,
    IS_IMPUTED,
]

# Data contract (Members 1 + 2) — DRAFT

Source of truth in code: [`src/solarcast/schemas.py`](../src/solarcast/schemas.py).
Processed file: `data/processed/hourly.parquet` (DVC-tracked, mirrored in S3 `processed/`).

| Column              | Type            | Unit   | Rule                                            |
|---------------------|-----------------|--------|-------------------------------------------------|
| `timestamp`         | datetime, UTC   | —      | start of hour, unique per `site_id`, no gaps    |
| `site_id`           | str             | —      | from `configs/sites.yaml`                       |
| `source`            | str             | —      | `pvgis` or `inverter`                           |
| `is_simulated`      | bool            | —      | True for PVGIS; reported separately             |
| `generation_kwh`    | float           | kWh    | 0 ≤ x ≤ 1.1 × capacity; 0 at night              |
| `ghi_wm2`           | float           | W/m²   | 0–1400                                          |
| `temp_c`            | float           | °C     | −5 to 55                                        |
| `cloud_cover_pct`   | float           | %      | 0–100                                           |
| `rel_humidity_pct`  | float           | %      | 0–100                                           |
| `wind_speed_ms`     | float           | m/s    | ≥ 0                                             |
| `panel_capacity_kw` | float           | kW     | > 0, constant per site                          |

## Missing-data rules (to agree)
- Gaps ≤ 3 h: linear interpolation (`params.yaml: data.max_gap_hours_interpolate`).
- Longer gaps: rows dropped; windows overlapping them are skipped by Member 2.
- Duplicate timestamps: keep last.

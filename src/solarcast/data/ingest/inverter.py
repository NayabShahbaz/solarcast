"""[Member 1] Real inverter exports: SolarMax inverter via the "Solar of Things" portal.

The portal exports three kinds of Excel file. Each one is recognised from its header, so file
names don't matter (and are never copied into the cleaned data):

| Export                    | Rows                      | What we keep                             |
|---------------------------|---------------------------|------------------------------------------|
| Device "MonthlyReport"    | one per day               | daily kWh + 24 hourly kWh columns        |
| Owner "MonthlyReport"     | one per day               | daily kWh                                |
| Device "DailyReport"      | one per ~5-minute reading | PV power/voltage, battery %, charging A  |

Facts checked against the real exports (docs/data_contract.md, "Real site"):
- The 24 hourly columns are in China time (UTC+8, the portal's timezone): column k covers
  local hour [k-1, k). They match the 5-minute data with correlation 0.987 under UTC+8, and
  worse with a 1-hour shift either way.
- Those hourly columns read ~9 % low. The daily total matches the 5-minute readings exactly,
  so the cleaning step (solarcast.data.real) rescales the hours to the daily total.
- 5-minute timestamps carry their own UTC offset (+05:00). A file without offsets is rejected
  rather than guessed.

Raw exports live in data/inverter/<folder>/ on the owner's machine only (git-ignored, not
pushed). Identifiers (serial number, device name, portal user name) are dropped here: nothing
these functions return contains them.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from solarcast import schemas as S

DATE = "date"            # portal calendar day (China time; the boundary falls at 21:00 PKT)
DAILY_KWH = "daily_kwh"
HOUR_COL = "hour_col"    # 1..24 as printed in the export
HOURLY_RAW_KWH = "hourly_raw_kwh"
REPORT = "report"        # "device_monthly" | "owner_monthly"

PV_KW = "pv_kw"
PV_V = "pv_v"
BATTERY_PCT = "battery_pct"
CHARGE_A = "charge_a"

_DAILY_HEADER = "Daily Generated Power (kWh)"
_HOURLY_HEADER = "Power generation period (kWh)"
_SNAPSHOT_COLUMNS = {    # export column -> our column; nothing else is ever read
    "Time": S.TIMESTAMP,
    "PV Input Power (kW)": PV_KW,
    "PV Input Voltage (V)": PV_V,
    "Battery Capacity (%)": BATTERY_PCT,
    "Battery Charging Current (A)": CHARGE_A,
}
_SNAPSHOT_REQUIRED = ("Time", "PV Input Power (kW)", "PV Input Voltage (V)")

# the portal writes workbooks without a style sheet; openpyxl warns on every file, harmlessly
warnings.filterwarnings("ignore", message="Workbook contains no default style", module="openpyxl")


class ExportFormatError(ValueError):
    """The file doesn't look like a known export. The message names the file and the reason."""


def classify(path: Path) -> str:
    """'device_monthly' | 'owner_monthly' | 'snapshots', from the header row."""
    header = pd.read_excel(path, header=None, nrows=1, dtype=str).iloc[0].dropna().tolist()
    if _HOURLY_HEADER in header and _DAILY_HEADER in header:
        return "device_monthly"
    if header[:2] == ["Time", _DAILY_HEADER]:
        return "owner_monthly"
    if all(c in header for c in _SNAPSHOT_REQUIRED):
        return "snapshots"
    raise ExportFormatError(f"{path.name}: unknown export layout (header starts {header[:5]})")


def read_device_monthly(path: Path, hour_tz: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (daily [date, daily_kwh, report], hourly [timestamp UTC, date, hour_col, hourly_raw_kwh]).

    Two-row header: names in row 0, hour numbers 1..24 in row 1 under "Power generation period
    (kWh)". Hourly cells are empty for days before the portal started recording them; those days
    only contribute a daily total.
    """
    raw = pd.read_excel(path, header=None, dtype=str)
    names = raw.iloc[0].tolist()
    try:
        c_time, c_daily, c_hour = (names.index(n) for n in ("Time", _DAILY_HEADER, _HOURLY_HEADER))
    except ValueError as e:
        raise ExportFormatError(f"{path.name}: missing column ({e})") from e
    labels = pd.to_numeric(raw.iloc[1, c_hour:c_hour + 24], errors="coerce").tolist()
    if labels != list(range(1, 25)):
        raise ExportFormatError(f"{path.name}: hourly columns are not labelled 1..24: {labels}")

    body = raw.iloc[2:]
    body = body[body[c_time].str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)]
    dates = pd.to_datetime(body[c_time], format="%Y-%m-%d")
    daily = pd.DataFrame({
        DATE: dates.to_numpy(),
        DAILY_KWH: pd.to_numeric(body[c_daily], errors="raise").to_numpy(),
        REPORT: "device_monthly",
    })

    hours = body.iloc[:, c_hour:c_hour + 24].apply(pd.to_numeric, errors="raise")
    hours.columns = range(1, 25)
    hours.index = pd.DatetimeIndex(dates.to_numpy(), name=DATE)
    long = hours.stack().rename(HOURLY_RAW_KWH).rename_axis([DATE, HOUR_COL]).reset_index()
    local = long[DATE] + pd.to_timedelta(long[HOUR_COL] - 1, unit="h")
    long.insert(0, S.TIMESTAMP, local.dt.tz_localize(hour_tz).dt.tz_convert("UTC"))
    return daily, long


def read_owner_monthly(path: Path) -> pd.DataFrame:
    """-> daily [date, daily_kwh, report]."""
    df = pd.read_excel(path, dtype=str)
    return pd.DataFrame({
        DATE: pd.to_datetime(df["Time"], format="%Y-%m-%d"),
        DAILY_KWH: pd.to_numeric(df[_DAILY_HEADER], errors="raise"),
        REPORT: "owner_monthly",
    })


def read_snapshots(path: Path) -> pd.DataFrame:
    """-> 5-minute readings [timestamp UTC, pv_kw, pv_v, battery_pct?, charge_a?].

    The battery columns are optional (they may be unticked in the export). Without them the
    'held back' check can't run for those hours.
    """
    present = pd.read_excel(path, nrows=0).columns
    use = [c for c in _SNAPSHOT_COLUMNS if c in present]
    df = pd.read_excel(path, usecols=use).rename(columns=_SNAPSHOT_COLUMNS)
    ts = df[S.TIMESTAMP].astype(str)
    if not ts.str.contains(r"[+-]\d{2}:\d{2}$", regex=True).all():
        raise ExportFormatError(f"{path.name}: some timestamps have no UTC offset - can't place them")
    df[S.TIMESTAMP] = pd.to_datetime(ts, utc=True)
    return df


def read_folder(folder: Path, hour_tz: str) -> dict:
    """Read every export in a folder.

    Returns {'daily', 'hourly', 'snapshots', 'files', 'conflicts'}: duplicates removed, and
    'conflicts' lists days whose total differs between two exports (kept: the device report).
    """
    files = sorted(p for p in folder.glob("*.xls*") if not p.name.startswith("~$"))
    if not files:
        raise FileNotFoundError(f"no inverter exports in {folder}")
    daily, hourly, snaps, kinds = [], [], [], {}
    for p in files:
        kind = classify(p)
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "device_monthly":
            d, h = read_device_monthly(p, hour_tz)
            daily.append(d)
            hourly.append(h)
        elif kind == "owner_monthly":
            daily.append(read_owner_monthly(p))
        else:
            snaps.append(read_snapshots(p))

    d = pd.concat(daily, ignore_index=True)
    spread = d.groupby(DATE)[DAILY_KWH].agg(lambda x: x.max() - x.min())
    conflicts = spread[spread > 0.05]
    # device reports carry the hourly detail, so they win if a day is in both
    d = (d.sort_values([DATE, REPORT]).drop_duplicates(DATE, keep="first")
         .reset_index(drop=True))
    h = (pd.concat(hourly, ignore_index=True).drop_duplicates(S.TIMESTAMP, keep="last")
         .sort_values(S.TIMESTAMP).reset_index(drop=True)) if hourly else pd.DataFrame()
    s = (pd.concat(snaps, ignore_index=True).drop_duplicates(S.TIMESTAMP, keep="last")
         .sort_values(S.TIMESTAMP).reset_index(drop=True)) if snaps else pd.DataFrame()
    return {"daily": d, "hourly": h, "snapshots": s, "files": kinds,
            "conflicts": {str(k.date()): round(float(v), 3) for k, v in conflicts.items()}}

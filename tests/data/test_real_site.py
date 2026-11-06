"""Real-site loader: synthetic exports shaped like the Solar of Things portal's files."""

import numpy as np
import openpyxl
import pandas as pd
import pytest

from solarcast import schemas as S
from solarcast.data import real
from solarcast.data.ingest import inverter as inv

SITE = {
    "site_id": "lahore_home_test", "source": "inverter", "is_simulated": False,
    "latitude": 31.44, "longitude": 74.29, "installed": "2026-08-01",
    "export_folder": "home_test", "export_hour_timezone": "Asia/Shanghai",
    "capacity_history": None, "tilt_deg": None, "azimuth_deg": 180,
}
# a sunny-day shape in CHINA time (portal columns): PKT 06-18h = China 09-21h
SHAPE = np.array([0.02] * 8 + [0.2, 0.5, 1.0, 1.6, 2.2, 2.6, 2.8, 2.7, 2.3, 1.7, 1.0, 0.4, 0.1]
                 + [0.02] * 3)


def _xlsx(path, rows):
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    wb.save(path)
    return path


def device_monthly(path, days, hourly=True, daily_factor=1.1, low_day=None):
    head = ["Device Serial Number", "Device Name", "Time", "Daily Generated Power (kWh)",
            "Power generation period (kWh)"] + [None] * 23
    rows = [head, [None] * 4 + list(range(1, 25))]
    for i, d in enumerate(days):
        h = SHAPE * (0.01 if d == low_day else 1.0)
        rows.append(["SERIAL-123", "My Inverter", d, f"{h.sum() * daily_factor:.3f}"]
                    + ([f"{x:.3f}" for x in h] if hourly else [None] * 24))
    return _xlsx(path, rows)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(real, "INVERTER_DIR", tmp_path)
    (tmp_path / "home_test").mkdir()
    return tmp_path / "home_test"


@pytest.fixture
def sun():
    days = pd.date_range("2026-08-01", "2026-08-31")
    return pd.Series(6.0, index=days)  # kWh/m^2 every day


def test_classify_all_three_exports_and_reject_unknown(folder):
    dm = device_monthly(folder / "a.xlsx", ["2026-08-01"])
    om = _xlsx(folder / "b.xlsx", [["Time", "Daily Generated Power (kWh)"], ["2026-08-01", "9.1"]])
    sn = _xlsx(folder / "c.xlsx", [["Device Serial Number", "Time", "PV Input Power (kW)",
                                    "PV Input Voltage (V)"], ["X", "2026-08-01 12:00:00+05:00", 1, 300]])
    bad = _xlsx(folder / "d.xlsx", [["foo", "bar"]])
    assert [inv.classify(p) for p in (dm, om, sn)] == ["device_monthly", "owner_monthly", "snapshots"]
    with pytest.raises(inv.ExportFormatError):
        inv.classify(bad)


def test_hour_columns_are_china_time(folder):
    _, hourly = inv.read_device_monthly(device_monthly(folder / "a.xlsx", ["2026-08-29"]),
                                        "Asia/Shanghai")
    row = hourly[hourly[inv.HOUR_COL] == 15].iloc[0]           # China 14:00-15:00
    assert row[S.TIMESTAMP] == pd.Timestamp("2026-08-29 06:00", tz="UTC")  # = PKT 11:00


def test_snapshots_need_utc_offsets_and_drop_identifiers(folder):
    ok = _xlsx(folder / "ok.xlsx", [["Device Serial Number", "Device Name", "Time",
                                     "PV Input Power (kW)", "PV Input Voltage (V)"],
                                    ["SERIAL-123", "My Inverter", "2026-08-01 12:00:00+05:00", 1.5, 390]])
    df = inv.read_snapshots(ok)
    assert set(df.columns) == {S.TIMESTAMP, inv.PV_KW, inv.PV_V}
    assert df[S.TIMESTAMP].iloc[0] == pd.Timestamp("2026-08-01 07:00", tz="UTC")
    naive = _xlsx(folder / "naive.xlsx", [["Time", "PV Input Power (kW)", "PV Input Voltage (V)"],
                                          ["2026-08-01 12:00:00", 1.5, 390]])
    with pytest.raises(inv.ExportFormatError, match="offset"):
        inv.read_snapshots(naive)


def test_export_hours_rescaled_to_daily_total_and_night_zeroed(folder, sun):
    days = [f"2026-08-{d:02d}" for d in range(1, 21)]
    device_monthly(folder / "a.xlsx", days, daily_factor=1.1)
    hourly, daily, _ = real.build_site(SITE, sun=sun)
    h = hourly[~hourly[real.IS_PARTIAL]].copy()
    h["day"] = real.portal_day(h[S.TIMESTAMP], "Asia/Shanghai").to_numpy()
    sums = h.groupby("day")[S.GENERATION_KWH].sum()
    night_raw = 0.02 * 11            # the 11 noise hours that are night at this site/time of year
    expected = daily.set_index(inv.DATE)[S.GENERATION_KWH] - night_raw
    assert np.allclose(sums, expected.reindex(sums.index), atol=0.05)
    pkt = h[S.TIMESTAMP].dt.tz_convert("Asia/Karachi").dt.hour
    assert (h.loc[pkt.isin([0, 1, 2, 3, 22, 23]), S.GENERATION_KWH] == 0).all()
    assert h[real.IS_SCALED].any()


def test_outage_day_flagged_but_kept(folder, sun):
    days = [f"2026-08-{d:02d}" for d in range(1, 21)]
    device_monthly(folder / "a.xlsx", days, low_day="2026-08-10")
    hourly, daily, summary = real.build_site(SITE, sun=sun)
    flagged = daily.set_index(inv.DATE)[real.IS_OUTAGE]
    assert flagged[pd.Timestamp("2026-08-10")]
    assert not flagged.drop(pd.Timestamp("2026-08-10")).fillna(False).any()
    assert summary["daily"]["outage_days"] == ["2026-08-10"]
    day10 = real.portal_day(hourly[S.TIMESTAMP], "Asia/Shanghai") == pd.Timestamp("2026-08-10")
    assert not hourly.loc[day10.to_numpy(), real.USABLE].any()


def test_held_back_only_when_battery_full_in_daylight(folder):
    ts = pd.date_range("2026-08-05 06:00", "2026-08-05 08:55", freq="5min", tz="UTC")  # PKT 11-14h
    rows = [["Time", "PV Input Power (kW)", "PV Input Voltage (V)", "Battery Capacity (%)",
             "Battery Charging Current (A)"]]
    for t in ts:
        full = t.hour == 7                                     # battery full only 07-08 UTC
        rows.append([t.tz_convert("Asia/Karachi").isoformat(), 1.0, 390,
                     100 if full else 80, 0 if full else 10])
    snaps = inv.read_snapshots(_xlsx(folder / "s.xlsx", rows))
    out = real.hourly_from_snapshots(snaps, SITE, real.params()["real_site"]).set_index(S.TIMESTAMP)
    assert out.loc[pd.Timestamp("2026-08-05 07:00", tz="UTC"), real.HELD_BACK]
    assert not out.loc[pd.Timestamp("2026-08-05 06:00", tz="UTC"), real.HELD_BACK]


def test_sun_elevation_is_sane_for_lahore():
    noon = pd.DatetimeIndex([pd.Timestamp("2026-06-21 07:00", tz="UTC")])   # ~12:00 PKT
    midnight = pd.DatetimeIndex([pd.Timestamp("2026-06-21 19:00", tz="UTC")])
    assert 75 < real.sun_elevation_deg(noon, 31.44, 74.29)[0] < 85
    assert real.sun_elevation_deg(midnight, 31.44, 74.29)[0] < -20

"""Look inside the pipeline's parquet files (they are binary, so a text editor can't open them).

    python scripts/peek_data.py                      # list every data file with its shape
    python scripts/peek_data.py data/raw/pvgis       # columns, types and a daytime sample
    python scripts/peek_data.py data/processed/hourly.parquet --rows 48
    python scripts/peek_data.py data/raw/open_meteo --csv   # export to data/interim/preview/ (git-ignored)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PREVIEW_DIR = ROOT / "data" / "interim" / "preview"


def _files(target: Path) -> list[Path]:
    return [target] if target.is_file() else sorted(target.rglob("*.parquet"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("path", nargs="?", default="data", help="parquet file or folder (default: data)")
    ap.add_argument("--rows", type=int, default=6, help="sample rows to print (default 6)")
    ap.add_argument("--csv", action="store_true", help="also export each file to CSV")
    a = ap.parse_args(argv)

    target = (ROOT / a.path) if not Path(a.path).is_absolute() else Path(a.path)
    files = _files(target)
    if not files:
        print(f"no parquet files under {target} - run `dvc pull` first")
        return 1

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 50)
    listing = a.path == "data"
    for f in files:
        df = pd.read_parquet(f)
        rel = f.relative_to(ROOT)
        if listing:
            print(f"{df.shape[0]:>7} rows x {df.shape[1]:>2} cols  {rel}")
            continue
        print(f"\n===== {rel}  ({df.shape[0]} rows x {df.shape[1]} cols)")
        print(df.dtypes.to_string())
        ts = df.get("timestamp")
        if ts is not None:
            print(f"range: {ts.min()} -> {ts.max()}")
        # start the sample at a daylight hour, so it isn't all night-time zeros
        ghi = next((c for c in ("ghi_wm2", "generation_kwh") if c in df), None)
        start = int((df[ghi] > 0).idxmax()) if ghi else 0
        print(df.iloc[start:start + a.rows].to_string(index=False))
        if a.csv:
            out = PREVIEW_DIR / f"{f.parent.name}_{f.stem}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out, index=False)
            print(f"-> {out.relative_to(ROOT)}")
    if listing:
        print("\nPass a file or folder to see its columns and a sample, e.g. "
              "python scripts/peek_data.py data/raw/pvgis")
    return 0


if __name__ == "__main__":
    sys.exit(main())

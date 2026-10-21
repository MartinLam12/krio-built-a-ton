"""
Shared data access for the dashboard.

All widgets should load the fire-statistics data through `load_fire_data()` so
there's a single, cached source of truth. Do not read the parquet file directly
in your widget module -- call this instead.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
PARQUET_FILE = DATA_DIR / "dnr_fire_statistics.parquet"
CSV_FILE = DATA_DIR / "dnr_fire_statistics.csv"

# Weekly U.S. Drought Monitor DSCI for Washington (from drought_data_pull.py).
DROUGHT_FILE = DATA_DIR / "wa_drought_dsci.csv"


def _data_file() -> Path | None:
    """Return the available data file, preferring parquet, else CSV, else None."""
    if PARQUET_FILE.exists():
        return PARQUET_FILE
    if CSV_FILE.exists():
        return CSV_FILE
    return None


@lru_cache(maxsize=1)
def load_fire_data() -> pd.DataFrame:
    """
    Load the WA DNR fire-statistics data and add a few convenience columns.

    Reads parquet if present, otherwise CSV (the fallback format used on
    platforms without a parquet engine, e.g. Windows-on-ARM). Cached so
    repeated calls across widgets don't re-read the file.

    Returns an empty DataFrame (not an error) if no data file is present, so the
    app still boots and individual widgets can show a friendly message. Run
    `python fire_data_pull.py` to generate the data file.
    """
    path = _data_file()
    if path is None:
        return pd.DataFrame()

    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)

    # DSCVR_DT is epoch milliseconds -> real datetime + year for convenience.
    if "DSCVR_DT" in df.columns:
        df["DSCVR_DATE"] = pd.to_datetime(df["DSCVR_DT"], unit="ms", errors="coerce")
        df["DSCVR_YEAR"] = df["DSCVR_DATE"].dt.year

    if "ACRES_BURNED" in df.columns:
        df["ACRES_BURNED"] = df["ACRES_BURNED"].fillna(0).round(2)

    return df


def data_available() -> bool:
    """True if a data file (parquet or CSV) exists on disk."""
    return _data_file() is not None


@lru_cache(maxsize=1)
def load_drought_data() -> pd.DataFrame:
    """
    Load the weekly U.S. Drought Monitor DSCI series for Washington.

    Source: drought_data_pull.py (US Drought Monitor REST API). Columns:
      DATE  : weekly map date (datetime)
      DSCI  : Drought Severity & Coverage Index, 0-500 (higher = worse drought)
      YEAR, MONTH : convenience fields derived from DATE

    Returns an empty DataFrame if the file is missing, so widgets can degrade
    gracefully. Run `python drought_data_pull.py` to generate it.
    """
    if not DROUGHT_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(DROUGHT_FILE)
    # The pull script may save either the raw API columns (MapDate) or the
    # already-cleaned ones (DATE); handle both for robustness.
    if "MapDate" in df.columns:
        df["DATE"] = pd.to_datetime(df["MapDate"].astype(str), format="%Y%m%d",
                                    errors="coerce")
    elif "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    if "DSCI" in df.columns:
        df["DSCI"] = pd.to_numeric(df["DSCI"], errors="coerce")

    if "DATE" in df.columns:
        df["YEAR"] = df["DATE"].dt.year
        df["MONTH"] = df["DATE"].dt.month

    return df.dropna(subset=["DATE"]).sort_values("DATE").reset_index(drop=True)


def drought_available() -> bool:
    """True if the drought data file exists on disk."""
    return DROUGHT_FILE.exists()

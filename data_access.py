"""
Shared data access for the dashboard.

All widgets should load the fire-statistics data through `load_fire_data()` so
there's a single, cached source of truth. Do not read the parquet file directly
in your widget module -- call this instead.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_FILE = Path(__file__).parent / "data" / "dnr_fire_statistics.parquet"


@lru_cache(maxsize=1)
def load_fire_data() -> pd.DataFrame:
    """
    Load the WA DNR fire-statistics parquet and add a few convenience columns.

    Cached so repeated calls across widgets don't re-read the file.

    Returns an empty DataFrame (not an error) if the parquet is missing, so the
    app still boots and individual widgets can show a friendly message. Run
    `python fire_data_pull.py` to generate the data file.
    """
    if not DATA_FILE.exists():
        return pd.DataFrame()

    df = pd.read_parquet(DATA_FILE)

    # DSCVR_DT is epoch milliseconds -> real datetime + year for convenience.
    if "DSCVR_DT" in df.columns:
        df["DSCVR_DATE"] = pd.to_datetime(df["DSCVR_DT"], unit="ms", errors="coerce")
        df["DSCVR_YEAR"] = df["DSCVR_DATE"].dt.year

    if "ACRES_BURNED" in df.columns:
        df["ACRES_BURNED"] = df["ACRES_BURNED"].fillna(0).round(2)

    return df


def data_available() -> bool:
    """True if the parquet data file exists on disk."""
    return DATA_FILE.exists()

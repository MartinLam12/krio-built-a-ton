"""
Data access layer for Washington Wildfire Watch.

Pulls the public "DNR Fire Statistics 2008-Present" point layer from the
Washington State DNR ArcGIS REST service (published on geo.wa.gov) and
normalizes it into a tidy pandas DataFrame.

Source layer:
  https://gis.dnr.wa.gov/site3/rest/services/Public_Wildfire/
  WADNR_PUBLIC_WD_WildFire_Data/MapServer/2
"""

from __future__ import annotations

import os
import time

import pandas as pd
import requests

LAYER_URL = (
    "https://gis.dnr.wa.gov/site3/rest/services/Public_Wildfire/"
    "WADNR_PUBLIC_WD_WildFire_Data/MapServer/2"
)
QUERY_URL = f"{LAYER_URL}/query"

# Fields we care about for the MVP. Keeping the list tight makes each
# page smaller and the download faster.
OUT_FIELDS = [
    "OBJECTID",
    "INCIDENT_NM",
    "COUNTY_LABEL_NM",
    "REGION_NAME",
    "FIREGCAUSE_LABEL_NM",
    "ACRES_BURNED",
    "DSCVR_DT",
    "LAT_COORD",
    "LON_COORD",
    "PROTECTION_TYPE",
]

# Where we cache the download so we are not hammering the state service
# on every dashboard reload.
CACHE_PATH = os.path.join(os.path.dirname(__file__), "wildfire_cache.parquet")
CACHE_TTL_SECONDS = 60 * 60 * 24  # one day


def _fetch_page(offset: int, page_size: int, timeout: int = 60) -> list[dict]:
    """Fetch a single page of records from the REST service."""
    params = {
        "where": "1=1",
        "outFields": ",".join(OUT_FIELDS),
        "orderByFields": "OBJECTID ASC",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "returnGeometry": "false",
        "f": "json",
    }
    resp = requests.get(QUERY_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"ArcGIS error: {payload['error']}")
    return [feat["attributes"] for feat in payload.get("features", [])]


def download_all(page_size: int = 2000, max_pages: int = 100) -> pd.DataFrame:
    """Page through the full layer and return a raw DataFrame."""
    rows: list[dict] = []
    for page in range(max_pages):
        offset = page * page_size
        batch = _fetch_page(offset, page_size)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        time.sleep(0.2)  # be polite to the public service
    return pd.DataFrame(rows)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize types and derive helper columns."""
    df = df.copy()

    # Discovery date arrives as epoch milliseconds (UTC).
    df["DSCVR_DT"] = pd.to_datetime(df["DSCVR_DT"], unit="ms", errors="coerce")
    df["year"] = df["DSCVR_DT"].dt.year
    df["month"] = df["DSCVR_DT"].dt.month

    df["ACRES_BURNED"] = pd.to_numeric(df["ACRES_BURNED"], errors="coerce").fillna(0.0)

    # Tidy up the string label columns.
    for col in ["COUNTY_LABEL_NM", "REGION_NAME", "FIREGCAUSE_LABEL_NM", "PROTECTION_TYPE"]:
        df[col] = df[col].fillna("Unknown").astype(str).str.strip()
    df.loc[df["FIREGCAUSE_LABEL_NM"].isin(["", "nan", "None"]), "FIREGCAUSE_LABEL_NM"] = "Undetermined"

    # Numeric lat/lon; drop rows we cannot place on a map.
    df["LAT_COORD"] = pd.to_numeric(df["LAT_COORD"], errors="coerce")
    df["LON_COORD"] = pd.to_numeric(df["LON_COORD"], errors="coerce")

    # Keep rows with a usable year even if coordinates are missing (they
    # still count toward county/cause stats). Map views filter coords later.
    df = df[df["year"].notna()].copy()
    df["year"] = df["year"].astype(int)
    return df


def load(force_refresh: bool = False) -> pd.DataFrame:
    """
    Return the cleaned wildfire DataFrame, using a local cache when fresh.

    Set ``force_refresh=True`` to bypass the cache and re-download.
    """
    if not force_refresh and os.path.exists(CACHE_PATH):
        age = time.time() - os.path.getmtime(CACHE_PATH)
        if age < CACHE_TTL_SECONDS:
            try:
                return pd.read_parquet(CACHE_PATH)
            except Exception:
                pass  # corrupt cache -> fall through to re-download

    raw = download_all()
    clean = _clean(raw)
    try:
        clean.to_parquet(CACHE_PATH, index=False)
    except Exception:
        # Parquet engine may be missing; the app still works without a cache.
        pass
    return clean


if __name__ == "__main__":
    frame = load(force_refresh=True)
    print(f"Loaded {len(frame):,} fire records")
    print(f"Years: {frame['year'].min()} - {frame['year'].max()}")
    print(f"Total acres burned: {frame['ACRES_BURNED'].sum():,.0f}")
    print(frame.head())

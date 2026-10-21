"""
Pull DNR Fire Statistics (2008-Present) from the Washington DNR ArcGIS REST service,
parse into a pandas DataFrame, and save to data/ (parquet if an engine is
available, otherwise CSV as a fallback for platforms without a parquet wheel).

Source layer:
https://gis.dnr.wa.gov/site3/rest/services/Public_Wildfire/WADNR_PUBLIC_WD_WildFire_Data/MapServer/2
(DNR Fire Statistics 2008-Present)
"""

from pathlib import Path

import pandas as pd
import requests

# ArcGIS REST query endpoint for the "DNR Fire Statistics 2008-Present" layer (ID 2)
BASE_URL = (
    "https://gis.dnr.wa.gov/site3/rest/services/Public_Wildfire/"
    "WADNR_PUBLIC_WD_WildFire_Data/MapServer/2/query"
)

# The service caps results at 2000 rows per request, so we paginate with resultOffset.
PAGE_SIZE = 2000

OUTPUT_DIR = Path(__file__).parent / "data"
PARQUET_FILE = OUTPUT_DIR / "dnr_fire_statistics.parquet"
CSV_FILE = OUTPUT_DIR / "dnr_fire_statistics.csv"


def get_total_count(session: requests.Session) -> int:
    """Return the total number of records in the layer."""
    params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
    resp = session.get(BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()["count"]


def fetch_all_records(session: requests.Session) -> list[dict]:
    """Page through the service and collect all feature attribute records."""
    records: list[dict] = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "orderByFields": "OBJECTID",
            "f": "json",
        }
        resp = session.get(BASE_URL, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            break

        records.extend(feature["attributes"] for feature in features)
        print(f"  fetched {len(records)} records...")

        # If the service returned fewer than a full page, we're done.
        if len(features) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return records


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        total = get_total_count(session)
        print(f"Total records reported by service: {total}")

        print("Pulling data (paginated)...")
        records = fetch_all_records(session)

    df = pd.DataFrame(records)
    print(f"\nDataFrame shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print("\nPreview:")
    print(df.head())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Prefer parquet (smaller, typed), but fall back to CSV when no parquet
    # engine is available -- e.g. on Windows-on-ARM, where neither pyarrow nor
    # a working fastparquet has a wheel. data_access.load_fire_data() reads
    # whichever file exists, so the dashboard works either way.
    try:
        df.to_parquet(PARQUET_FILE, index=False)
        print(f"\nSaved {len(df)} rows to {PARQUET_FILE}")
    except Exception as exc:  # noqa: BLE001 - any missing-engine error -> CSV
        print(f"\nParquet engine unavailable ({exc.__class__.__name__}); "
              f"writing CSV instead.")
        df.to_csv(CSV_FILE, index=False)
        print(f"Saved {len(df)} rows to {CSV_FILE}")


if __name__ == "__main__":
    main()

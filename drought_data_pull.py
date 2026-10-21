"""
Pull weekly Drought Severity & Coverage Index (DSCI) for Washington from the
U.S. Drought Monitor REST API and save to data/wa_drought_dsci.csv.

The DSCI is a single 0-500 value per week summarizing how much of the state is
in drought and how severe it is (higher = worse). Pairing this weekly series
with the DNR fire record gives a leading indicator for wildfire risk.

Source / API docs:
https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx

Example endpoint (Washington = FIPS 53):
https://usdmdataservices.unl.edu/api/StateStatistics/GetDSCI?aoi=53&startdate=1/1/2008&enddate=12/31/2026&statisticsType=1
"""

from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

# Washington's two-digit state FIPS code.
WA_FIPS = "53"

API_URL = "https://usdmdataservices.unl.edu/api/StateStatistics/GetDSCI"

# The U.S. Drought Monitor record starts in 2000; the DNR fire data starts in
# 2008, so we pull from 2008 to today to line the two series up.
START_DATE = "1/1/2008"

OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "wa_drought_dsci.csv"


def fetch_dsci(session: requests.Session) -> pd.DataFrame:
    """Fetch the weekly DSCI series for Washington as a DataFrame."""
    # Build the end date manually: Windows strftime lacks %-m / %-d.
    today = date.today()
    end_date = f"{today.month}/{today.day}/{today.year}"

    params = {
        "aoi": WA_FIPS,
        "startdate": START_DATE,
        "enddate": end_date,
        "statisticsType": "1",
    }
    headers = {"Accept": "application/json"}
    resp = session.get(API_URL, params=params, headers=headers, timeout=120)
    resp.raise_for_status()

    # The API returns JSON when asked, but falls back to CSV; handle both.
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype.lower():
        df = pd.DataFrame(resp.json())
    else:
        df = pd.read_csv(StringIO(resp.text))

    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize to columns DATE (datetime) and DSCI (int), sorted by date."""
    # Column names vary in case between JSON and CSV responses.
    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("mapdate") or cols.get("date")
    dsci_col = cols.get("dsci")
    if date_col is None or dsci_col is None:
        raise ValueError(f"Unexpected columns from API: {list(df.columns)}")

    raw_dates = df[date_col].astype(str).str.strip()
    # CSV responses give YYYYMMDD (e.g. "20231226"); JSON responses give an
    # ISO datetime (e.g. "2023-12-26T00:00:00"). Try the compact form first,
    # then fall back to general parsing for anything left.
    parsed = pd.to_datetime(raw_dates, format="%Y%m%d", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(raw_dates[missing], errors="coerce")

    out = pd.DataFrame(
        {"DATE": parsed, "DSCI": pd.to_numeric(df[dsci_col], errors="coerce")}
    )
    return out.dropna(subset=["DATE"]).sort_values("DATE").reset_index(drop=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        print("Pulling Washington weekly DSCI from the U.S. Drought Monitor...")
        raw = fetch_dsci(session)
        print(f"Received {len(raw)} weekly records.")

    df = clean(raw)
    print(f"\nCleaned shape: {df.shape}")
    if df.empty:
        raise SystemExit("No rows after cleaning -- check the API response format.")
    print(f"Date range: {df['DATE'].min().date()} -> {df['DATE'].max().date()}")
    dsci = df["DSCI"].dropna()
    if not dsci.empty:
        print(f"DSCI range: {int(dsci.min())} - {int(dsci.max())}")
    print("\nPreview:")
    print(df.head())

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(df)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

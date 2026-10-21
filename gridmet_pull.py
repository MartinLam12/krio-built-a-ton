"""
Pull GridMET fire-danger data for Washington State and save a compact grid.

GridMET (https://www.climatologylab.org/gridmet.html) is daily ~4km gridded
surface-meteorology data for CONUS. We use the Energy Release Component (ERC,
fuel model G / conifer) -- a standard wildfire-danger index -- as a weather/
fuel-dryness signal to enhance the expected-risk model.

We access it over OPeNDAP from the Northwest Knowledge Network THREDDS server,
subset to a Washington bounding box server-side (so we don't download CONUS),
and reduce the daily fire-season data to a single per-cell statistic
(90th-percentile ERC over Jun-Sep). The result is saved to
data/gridmet_erc_wa.parquet as a tidy lat/lon/erc table.

Run with:
    ..\\buildathon\\Scripts\\python.exe gridmet_pull.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# ERC, fuel model G (conifer forest). The "#fillmismatch" suffix is the
# workaround the GridMET maintainers document for netCDF fill-value issues.
VAR = "energy_release_component-g"
YEAR = 2024
OPENDAP_URL = (
    f"http://thredds.northwestknowledge.net/thredds/dodsC/MET/erc/"
    f"erc_{YEAR}.nc#fillmismatch"
)

# Washington bounding box.
WA_LAT = (45.0, 49.5)
WA_LON = (-125.0, -116.0)

# Fire season months used for the summary statistic.
FIRE_SEASON_MONTHS = (6, 7, 8, 9)
PERCENTILE = 0.90  # high-end ERC -> captures peak danger, not just the average

OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "gridmet_erc_wa.parquet"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Opening GridMET ERC {YEAR} over OPeNDAP...")
    ds = xr.open_dataset(OPENDAP_URL)

    # GridMET latitude is stored descending; order the slice to match.
    lat = ds["lat"].values
    lat_slice = (
        slice(WA_LAT[1], WA_LAT[0]) if lat[0] > lat[-1] else slice(*WA_LAT)
    )
    print("Subsetting to Washington...")
    sub = ds[VAR].sel(lat=lat_slice, lon=slice(*WA_LON))

    # Restrict to fire-season days and compute the per-cell high-end ERC.
    days = pd.to_datetime(ds["day"].values)
    season_idx = np.where(np.isin(days.month, FIRE_SEASON_MONTHS))[0]
    print(f"Reducing {len(season_idx)} fire-season days to the "
          f"{int(PERCENTILE * 100)}th percentile per cell...")
    season = sub.isel(day=season_idx)

    # Suppress the expected all-NaN (ocean / out-of-domain) warning.
    with np.errstate(invalid="ignore"):
        stat = season.quantile(PERCENTILE, dim="day")

    # Flatten the 2D grid into a tidy lat/lon/erc table, dropping NaN cells.
    df = stat.to_dataframe(name="erc").reset_index()
    df = df[["lat", "lon", "erc"]].dropna(subset=["erc"])
    df["erc"] = df["erc"].round(1)

    df.to_parquet(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(df):,} WA grid cells to {OUTPUT_FILE}")
    print(f"ERC range: {df['erc'].min()} - {df['erc'].max()} "
          f"(mean {df['erc'].mean():.1f})")


if __name__ == "__main__":
    main()

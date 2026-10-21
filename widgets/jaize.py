"""
Jaize's widget — Expected Fire Risk map.

WHAT THIS SHOWS
---------------
A gridded map of WHERE fires are EXPECTED, not just where they happened. Each
grid cell's score combines two ideas:

  1. Historical hazard  -- how often (and optionally how severely) the cell has
     burned historically. More past ignitions -> more expected future fire.

  2. Fuel-recovery timing -- a cell that burned recently is TEMPORARILY lower
     risk because the fuel burned off. Risk then climbs back as vegetation
     regrows. This is modeled with an explicit, tunable recovery curve so the
     "how long is an area low-risk after a fire" assumption is visible and
     documented, not hidden.

        expected_risk = historical_hazard * fuel_availability(years_since_fire)

FUEL RECOVERY MODEL
-------------------
After a fire, a cell's available fuel is low. It ramps back up to full over
FUEL_RECOVERY_YEARS. We model the ramp linearly from a small floor
(POST_FIRE_FLOOR) immediately after the fire up to 1.0 at full recovery.
These are the key, defensible assumptions — tune them as better fuels/
vegetation data becomes available.

CAVEATS (shown in the UI too)
-----------------------------
- This is RELATIVE expected risk from historical ignition patterns + fuel
  timing. It is not an absolute probability.
- It does not yet account for weather, drought, terrain/slope, or live
  vegetation/fuel type. Those are future data layers.
- Source data is DNR-protected/assisted fires, so non-DNR land may be
  undercounted.
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import panel as pn

from data_access import data_available, load_fire_data

TITLE = "Expected Fire Risk (Jaize)"

# --- Model constants (the key, documented assumptions) ---------------------

# Years after a fire until fuel is considered fully recovered / back to peak
# hazard. Mid-range value for WA mixed conifer / shrub systems; tunable.
FUEL_RECOVERY_YEARS = 15

# Fuel availability immediately AFTER a fire, as a fraction of peak (0-1).
# Not zero: some fine fuels return within a season. This is the low-risk floor.
POST_FIRE_FLOOR = 0.1

# Spatial grid resolution in degrees (~0.1 deg lat ~= 11 km). Smaller = finer.
GRID_DEG = 0.1

# WA-ish bounding box used to drop bad coordinates (0,0 etc.).
WA_LAT = (45.0, 49.5)
WA_LON = (-125.0, -116.0)

# "Current" year used to compute years-since-last-fire.
CURRENT_YEAR = datetime.now().year

# GridMET ERC (fire-danger) grid for Washington, produced by gridmet_pull.py.
# Used as an optional "weather danger" multiplier on the risk score.
ERC_FILE = Path(__file__).resolve().parent.parent / "data" / "gridmet_erc_wa.parquet"


@lru_cache(maxsize=1)
def _load_erc() -> "pd.DataFrame | None":
    """Load the GridMET ERC grid if present, else None. Cached."""
    if not ERC_FILE.exists():
        return None
    return pd.read_parquet(ERC_FILE)


def erc_available() -> bool:
    """True if the GridMET ERC weather layer has been pulled."""
    return ERC_FILE.exists()


def weather_danger_for(lats: np.ndarray, lons: np.ndarray) -> "np.ndarray | None":
    """
    Return a 0-1 'weather danger' multiplier per (lat, lon) from GridMET ERC.

    Uses a fast nearest-neighbor lookup by snapping each point to the closest
    GridMET cell (the ERC grid is ~4km, far finer than our fire grid, so
    nearest-cell is accurate enough). ERC is normalized to 0-1 across WA, so a
    cell sitting in the driest/most-dangerous conditions gets the full weight
    and a damp coastal cell gets much less. Returns None if ERC isn't pulled.
    """
    erc = _load_erc()
    if erc is None or erc.empty:
        return None

    erc_lat = erc["lat"].to_numpy()
    erc_lon = erc["lon"].to_numpy()
    erc_val = erc["erc"].to_numpy()

    # Normalize ERC across WA to 0-1 so it acts as a relative multiplier.
    lo, hi = erc_val.min(), erc_val.max()
    erc_norm = (erc_val - lo) / (hi - lo) if hi > lo else np.ones_like(erc_val)

    # Nearest ERC cell for each query point (vectorized; grid is small enough).
    out = np.empty(len(lats))
    for i, (la, lo_) in enumerate(zip(lats, lons)):
        j = np.argmin((erc_lat - la) ** 2 + (erc_lon - lo_) ** 2)
        out[i] = erc_norm[j]
    return out


def fuel_availability(years_since_fire: np.ndarray) -> np.ndarray:
    """
    Fraction of peak fuel available given years since the most recent fire.

    Linear ramp from POST_FIRE_FLOOR (just after a fire) up to 1.0 at
    FUEL_RECOVERY_YEARS, then flat at 1.0. This is the explicit "how long is a
    burned area low-risk" curve.
    """
    ramp = POST_FIRE_FLOOR + (1.0 - POST_FIRE_FLOOR) * (
        years_since_fire / FUEL_RECOVERY_YEARS
    )
    return np.clip(ramp, POST_FIRE_FLOOR, 1.0)


def compute_risk_grid(weight_by_acres: bool, use_weather: bool = True):
    """
    Aggregate fires into grid cells and compute expected-risk per cell.

    Returns a DataFrame with one row per cell: centroid lat/lon, fire count,
    years since the most recent fire, fuel availability, GridMET weather
    danger, and the final expected-risk score (normalized 0-1 for display).

        expected_risk = hazard * fuel_availability [* weather_danger]

    The weather_danger term (from GridMET ERC) is applied only when
    `use_weather` is True and the ERC layer has been pulled.
    """
    df = load_fire_data()
    df = df.dropna(subset=["LAT_COORD", "LON_COORD", "DSCVR_YEAR"])
    df = df[
        df["LAT_COORD"].between(*WA_LAT) & df["LON_COORD"].between(*WA_LON)
    ].copy()

    # Snap each fire to a grid cell (use the cell's lower corner as its id).
    df["cell_lat"] = (np.floor(df["LAT_COORD"] / GRID_DEG) * GRID_DEG).round(4)
    df["cell_lon"] = (np.floor(df["LON_COORD"] / GRID_DEG) * GRID_DEG).round(4)

    # Historical hazard: count of fires, optionally weighted by acres burned.
    agg = {
        "LAT_COORD": "size",            # fire count
        "DSCVR_YEAR": "max",            # most recent fire year in the cell
    }
    grouped = df.groupby(["cell_lat", "cell_lon"]).agg(agg)
    grouped.columns = ["fire_count", "last_fire_year"]

    if weight_by_acres:
        acres = df.groupby(["cell_lat", "cell_lon"])["ACRES_BURNED"].sum()
        # log1p keeps a few mega-fires from completely dominating the scale.
        grouped["hazard"] = grouped["fire_count"] * np.log1p(acres).reindex(
            grouped.index
        ).fillna(0)
    else:
        grouped["hazard"] = grouped["fire_count"].astype(float)

    grouped = grouped.reset_index()

    # Fuel-recovery timing.
    grouped["years_since_fire"] = (CURRENT_YEAR - grouped["last_fire_year"]).clip(
        lower=0
    )
    grouped["fuel_availability"] = fuel_availability(
        grouped["years_since_fire"].to_numpy()
    )

    # Cell centroids (also used for the ERC nearest-cell lookup).
    grouped["lat"] = grouped["cell_lat"] + GRID_DEG / 2
    grouped["lon"] = grouped["cell_lon"] + GRID_DEG / 2

    # Weather danger from GridMET ERC (0-1). Defaults to 1.0 (no effect) if the
    # layer isn't pulled or the user turned it off.
    grouped["weather_danger"] = 1.0
    if use_weather:
        wd = weather_danger_for(
            grouped["lat"].to_numpy(), grouped["lon"].to_numpy()
        )
        if wd is not None:
            grouped["weather_danger"] = wd

    # Expected risk = hazard * fuel availability * weather danger.
    grouped["expected_risk"] = (
        grouped["hazard"]
        * grouped["fuel_availability"]
        * grouped["weather_danger"]
    )

    # Normalize to 0-1 for a readable color scale.
    max_risk = grouped["expected_risk"].max()
    grouped["risk_norm"] = (
        grouped["expected_risk"] / max_risk if max_risk else 0.0
    )

    return grouped


def create_panel() -> pn.viewable.Viewable:
    """Return Jaize's expected-fire-risk map widget."""
    if not data_available():
        return pn.Column(
            f"## {TITLE}",
            pn.pane.Alert(
                "Data not found. Run `python fire_data_pull.py` first.",
                alert_type="warning",
            ),
            name=TITLE,
        )

    import hvplot.pandas  # noqa: F401  (registers the .hvplot accessor)

    # --- Controls ----------------------------------------------------------
    recovery_slider = pn.widgets.IntSlider(
        name="Fuel recovery years (low-risk window after a fire)",
        start=1,
        end=40,
        value=FUEL_RECOVERY_YEARS,
        step=1,
    )
    weight_toggle = pn.widgets.Checkbox(
        name="Weight hazard by acres burned (not just fire count)",
        value=True,
    )
    top_only = pn.widgets.Checkbox(
        name="Show only the highest-risk cells (top 25%)",
        value=False,
    )
    weather_toggle = pn.widgets.Checkbox(
        name="Apply GridMET weather danger (ERC fire-danger index)",
        value=erc_available(),
        disabled=not erc_available(),
    )

    @pn.depends(recovery_slider, weight_toggle, top_only, weather_toggle)
    def risk_map(recovery_years, weight_by_acres, top_quartile, use_weather):
        # Let the slider drive the recovery horizon live.
        global FUEL_RECOVERY_YEARS
        FUEL_RECOVERY_YEARS = recovery_years

        grid = compute_risk_grid(weight_by_acres, use_weather=use_weather)
        if grid.empty:
            return pn.pane.Markdown("### No mappable fire data.")

        if top_quartile:
            cutoff = grid["risk_norm"].quantile(0.75)
            grid = grid[grid["risk_norm"] >= cutoff]

        title = "Expected fire risk (historical hazard x fuel recovery"
        title += " x GridMET weather)" if use_weather else ")"

        return grid.hvplot.points(
            x="lon",
            y="lat",
            c="risk_norm",
            cmap="YlOrRd",
            clim=(0, 1),
            size=90,
            line_color="gray",
            line_width=0.3,
            title=title,
            height=440,
            responsive=True,
            hover_cols=[
                "fire_count",
                "last_fire_year",
                "years_since_fire",
                "fuel_availability",
                "weather_danger",
                "risk_norm",
            ],
            colorbar=True,
        ).opts(bgcolor="#f8f8f8")

    @pn.depends(recovery_slider)
    def recovery_note(recovery_years):
        return pn.pane.Markdown(
            f"**Fuel-recovery assumption:** after a fire, an area is modeled as "
            f"low-risk and recovers to peak fuel over **{recovery_years} years** "
            f"(starting from a {int(POST_FIRE_FLOOR * 100)}% floor right after the "
            f"burn). Cells that burned within this window are suppressed in the "
            f"risk score.",
            styles={"font-size": "13px", "color": "#374151"},
        )

    weather_status = (
        "GridMET ERC fire-danger layer loaded (fire-season 2024, 90th pct). "
        "Toggle it on/off above to see how dry/dangerous weather shifts the map."
        if erc_available()
        else "GridMET weather layer not found. Run `python gridmet_pull.py` to "
        "enable the ERC fire-danger multiplier."
    )
    weather_note = pn.pane.Markdown(
        f"**Weather layer:** {weather_status}",
        styles={"font-size": "13px", "color": "#374151"},
    )

    caveat = pn.pane.Alert(
        "Relative expected risk from historical ignitions + fuel timing"
        + (" + GridMET ERC weather danger" if erc_available() else "")
        + ". Not an absolute probability; does not yet include terrain or live "
        "vegetation. DNR-protected/assisted fires only.",
        alert_type="secondary",
    )

    controls = pn.Column(
        recovery_slider,
        weight_toggle,
        weather_toggle,
        top_only,
        recovery_note,
        weather_note,
    )

    risk_view = pn.Column(
        controls,
        risk_map,
        caveat,
        sizing_mode="stretch_width",
        name="Expected Risk",
    )

    # Live WA DNR Forest Health Tracker map, embedded as-is. Shows existing
    # forest-health treatment projects (thinning, Rx burn, etc.) so a manager
    # can compare where risk is high vs. where treatments already exist.
    tracker_embed = pn.Column(
        pn.pane.Markdown(
            "Live **WA DNR Forest Health Tracker** map of existing treatment "
            "projects. Compare against the expected-risk tab to spot high-risk "
            "areas that lack treatment coverage.",
            styles={"font-size": "13px", "color": "#374151"},
        ),
        pn.pane.HTML(
            """
            <iframe
                src="https://foresthealthtracker.dnr.wa.gov/projects/map"
                style="width:100%;height:600px;border:1px solid #e5e7eb;
                       border-radius:8px;"
                loading="lazy"
                title="WA DNR Forest Health Tracker map">
            </iframe>
            """,
            sizing_mode="stretch_width",
        ),
        pn.pane.Markdown(
            "Source: [foresthealthtracker.dnr.wa.gov]"
            "(https://foresthealthtracker.dnr.wa.gov/projects/map) (embedded "
            "live; data is the tracker's, not pulled into this app).",
            styles={"font-size": "12px", "color": "#6b7280"},
        ),
        sizing_mode="stretch_width",
        name="Forest Health Projects",
    )

    tabs = pn.Tabs(risk_view, tracker_embed)

    return pn.Column(
        f"## {TITLE}",
        tabs,
        name=TITLE,
        sizing_mode="stretch_width",
    )

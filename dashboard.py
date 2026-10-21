"""
Interactive Panel dashboard for the WA DNR Fire Statistics (2008-Present) dataset.

Run locally with:
    ..\\buildathon\\Scripts\\panel.exe serve dashboard.py --show

The dashboard provides summary metrics, filters (region / cause / year range),
a fires-per-year bar chart, a geographic scatter of fire locations, and a
filterable data table.
"""

from pathlib import Path

import pandas as pd
import panel as pn

pn.extension("tabulator", sizing_mode="stretch_width")

DATA_FILE = Path(__file__).parent / "data" / "dnr_fire_statistics.parquet"

# Columns worth showing in the table (friendly subset of the 38 raw columns).
TABLE_COLUMNS = [
    "INCIDENT_NM",
    "DSCVR_YEAR",
    "DSCVR_MONTH",
    "COUNTY_LABEL_NM",
    "REGION_NAME",
    "FIREGCAUSE_LABEL_NM",
    "ACRES_BURNED",
    "LAT_COORD",
    "LON_COORD",
]


def load_data() -> pd.DataFrame:
    """Load the parquet file and derive a few convenience columns."""
    df = pd.read_parquet(DATA_FILE)

    # DSCVR_DT is epoch milliseconds -> real datetime + year for filtering/plots.
    df["DSCVR_DATE"] = pd.to_datetime(df["DSCVR_DT"], unit="ms", errors="coerce")
    df["DSCVR_YEAR"] = df["DSCVR_DATE"].dt.year

    # Keep acres sane for display.
    df["ACRES_BURNED"] = df["ACRES_BURNED"].fillna(0).round(2)
    return df


df = load_data()

years = sorted(int(y) for y in df["DSCVR_YEAR"].dropna().unique())
min_year, max_year = years[0], years[-1]

# ---------------------------------------------------------------------------
# Widgets (filters)
# ---------------------------------------------------------------------------
region_select = pn.widgets.MultiChoice(
    name="Region",
    options=sorted(df["REGION_NAME"].dropna().unique().tolist()),
    placeholder="All regions",
)
cause_select = pn.widgets.MultiChoice(
    name="General cause",
    options=sorted(df["FIREGCAUSE_LABEL_NM"].dropna().unique().tolist()),
    placeholder="All causes",
)
year_range = pn.widgets.IntRangeSlider(
    name="Discovery year",
    start=min_year,
    end=max_year,
    value=(min_year, max_year),
    step=1,
)


def filter_data(region, cause, yr_range) -> pd.DataFrame:
    """Apply the active filters and return the filtered frame."""
    out = df
    lo, hi = yr_range
    out = out[(out["DSCVR_YEAR"] >= lo) & (out["DSCVR_YEAR"] <= hi)]
    if region:
        out = out[out["REGION_NAME"].isin(region)]
    if cause:
        out = out[out["FIREGCAUSE_LABEL_NM"].isin(cause)]
    return out


# ---------------------------------------------------------------------------
# Reactive views
# ---------------------------------------------------------------------------
@pn.depends(region_select, cause_select, year_range)
def summary_cards(region, cause, yr_range):
    data = filter_data(region, cause, yr_range)
    total_fires = len(data)
    total_acres = data["ACRES_BURNED"].sum()
    avg_acres = data["ACRES_BURNED"].mean() if total_fires else 0
    largest = data["ACRES_BURNED"].max() if total_fires else 0

    def card(title, value):
        return pn.pane.HTML(
            f"""
            <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
                        padding:16px 20px;box-shadow:0 1px 2px rgba(0,0,0,.05);">
              <div style="font-size:12px;color:#6b7280;text-transform:uppercase;
                          letter-spacing:.05em;">{title}</div>
              <div style="font-size:26px;font-weight:700;color:#b91c1c;margin-top:4px;">
                {value}
              </div>
            </div>
            """,
            sizing_mode="stretch_width",
        )

    return pn.Row(
        card("Total fires", f"{total_fires:,}"),
        card("Total acres burned", f"{total_acres:,.0f}"),
        card("Avg acres / fire", f"{avg_acres:,.1f}"),
        card("Largest fire (acres)", f"{largest:,.0f}"),
    )


@pn.depends(region_select, cause_select, year_range)
def fires_per_year(region, cause, yr_range):
    data = filter_data(region, cause, yr_range)
    by_year = (
        data.groupby("DSCVR_YEAR").size().rename("Fires").reset_index()
    )
    if by_year.empty:
        return pn.pane.Markdown("### No data for the current filters.")
    # Use the year as a categorical string so the bar chart treats the x-axis
    # as discrete categories (avoids a numeric-diff crash in holoviews/bokeh).
    by_year["Year"] = by_year["DSCVR_YEAR"].astype(int).astype(str)
    return by_year.hvplot.bar(
        x="Year",
        y="Fires",
        title="Fires discovered per year",
        color="#ef4444",
        height=320,
        rot=45,
    )


@pn.depends(region_select, cause_select, year_range)
def fire_map(region, cause, yr_range):
    data = filter_data(region, cause, yr_range)
    data = data.dropna(subset=["LAT_COORD", "LON_COORD"])
    # Drop obviously bad coordinates (0,0 etc.) and clip to WA-ish bounds.
    data = data[
        data["LAT_COORD"].between(45, 49.5) & data["LON_COORD"].between(-125, -116)
    ]
    if data.empty:
        return pn.pane.Markdown("### No mappable points for the current filters.")
    return data.hvplot.points(
        x="LON_COORD",
        y="LAT_COORD",
        c="ACRES_BURNED",
        cmap="YlOrRd",
        clim=(0, 500),
        size=20,
        title="Fire locations (color = acres burned)",
        height=420,
        hover_cols=["INCIDENT_NM", "COUNTY_LABEL_NM", "ACRES_BURNED"],
        geo=False,
    )


@pn.depends(region_select, cause_select, year_range)
def data_table(region, cause, yr_range):
    data = filter_data(region, cause, yr_range)[TABLE_COLUMNS]
    return pn.widgets.Tabulator(
        data,
        pagination="remote",
        page_size=20,
        height=480,
        layout="fit_data_stretch",
        theme="simple",
        disabled=True,
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
try:
    import hvplot.pandas  # noqa: F401  (registers the .hvplot accessor)

    charts_available = True
except ImportError:
    charts_available = False

sidebar = pn.Column(
    "## Filters",
    region_select,
    cause_select,
    year_range,
    pn.pane.Markdown(
        "Data: WA DNR Fire Statistics 2008-Present. "
        "Filters apply to every panel.",
        styles={"color": "#6b7280", "font-size": "12px"},
    ),
    width=300,
)

main_items = [summary_cards]
if charts_available:
    main_items += [pn.Row(fires_per_year), pn.Row(fire_map)]
else:
    main_items.append(
        pn.pane.Markdown(
            "> Charts need `hvplot`. Install with `uv pip install hvplot` to enable "
            "the year chart and map."
        )
    )
main_items.append(pn.pane.Markdown("### Fire records"))
main_items.append(data_table)

template = pn.template.FastListTemplate(
    title="WA DNR Fire Statistics (2008-Present)",
    header_background="#b91c1c",
    sidebar=[sidebar],
    main=main_items,
    accent_base_color="#b91c1c",
)

template.servable()

"""
Washington Wildfire Watch - MVP dashboard.

A "where to intervene" tool built on the public DNR Fire Statistics
2008-Present layer. It ranks Washington counties by wildfire burden and
lets you explore fire locations, causes, and trends interactively.

Run it with:
    panel serve app.py --show

Stack: Panel (layout + widgets), Bokeh (map), Plotly (charts).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import panel as pn
import plotly.express as px
import plotly.graph_objects as go
from bokeh.models import ColumnDataSource, HoverTool, LinearColorMapper, ColorBar
from bokeh.plotting import figure
from bokeh.transform import linear_cmap

import data_source

pn.extension("plotly", sizing_mode="stretch_width")

ACCENT = "#c1440e"  # wildfire orange-red

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
DF = data_source.load()

ALL_YEARS = (int(DF["year"].min()), int(DF["year"].max()))
COUNTIES = ["All counties"] + sorted(DF["COUNTY_LABEL_NM"].unique().tolist())
CAUSES = ["All causes"] + sorted(DF["FIREGCAUSE_LABEL_NM"].unique().tolist())


# ---------------------------------------------------------------------------
# Web Mercator helper (so points sit correctly on a tile map)
# ---------------------------------------------------------------------------
def lonlat_to_mercator(lon: pd.Series, lat: pd.Series) -> tuple[pd.Series, pd.Series]:
    k = 6378137.0
    x = lon * (k * np.pi / 180.0)
    y = np.log(np.tan((90.0 + lat) * np.pi / 360.0)) * k
    return x, y


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------
year_slider = pn.widgets.IntRangeSlider(
    name="Fire year", start=ALL_YEARS[0], end=ALL_YEARS[1],
    value=ALL_YEARS, step=1,
)
county_select = pn.widgets.Select(name="County", options=COUNTIES, value="All counties")
cause_select = pn.widgets.Select(name="Cause", options=CAUSES, value="All causes")
rank_metric = pn.widgets.RadioButtonGroup(
    name="Rank counties by",
    options={"Acres burned": "acres", "Fire count": "count", "Priority score": "score"},
    value="score",
)


def filter_df() -> pd.DataFrame:
    lo, hi = year_slider.value
    out = DF[(DF["year"] >= lo) & (DF["year"] <= hi)]
    if county_select.value != "All counties":
        out = out[out["COUNTY_LABEL_NM"] == county_select.value]
    if cause_select.value != "All causes":
        out = out[out["FIREGCAUSE_LABEL_NM"] == cause_select.value]
    return out


# ---------------------------------------------------------------------------
# Priority scoring: the core "where to intervene" logic
# ---------------------------------------------------------------------------
def county_rankings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rank counties by wildfire burden.

    Priority score blends three normalized signals:
      - total acres burned  (severity / footprint)
      - fire count          (frequency / ignition pressure)
      - recent activity      (acres in the most recent 5 years of the view)
    Each is scaled 0-1, then combined with transparent weights.
    """
    if df.empty:
        return pd.DataFrame(columns=["county", "fires", "acres", "recent_acres", "score"])

    recent_cutoff = df["year"].max() - 4
    grp = df.groupby("COUNTY_LABEL_NM")
    rank = grp.agg(fires=("OBJECTID", "count"), acres=("ACRES_BURNED", "sum")).reset_index()
    recent = (
        df[df["year"] >= recent_cutoff]
        .groupby("COUNTY_LABEL_NM")["ACRES_BURNED"].sum()
        .rename("recent_acres")
    )
    rank = rank.merge(recent, left_on="COUNTY_LABEL_NM", right_index=True, how="left")
    rank["recent_acres"] = rank["recent_acres"].fillna(0.0)
    rank = rank.rename(columns={"COUNTY_LABEL_NM": "county"})

    def norm(s: pd.Series) -> pd.Series:
        rng = s.max() - s.min()
        return (s - s.min()) / rng if rng else s * 0.0

    rank["score"] = (
        0.45 * norm(rank["acres"])
        + 0.30 * norm(rank["fires"])
        + 0.25 * norm(rank["recent_acres"])
    ) * 100.0
    return rank.sort_values("score", ascending=False)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
@pn.depends(year_slider, county_select, cause_select)
def kpi_row(*_):
    df = filter_df()
    fires = len(df)
    acres = df["ACRES_BURNED"].sum()
    big = int((df["ACRES_BURNED"] >= 100).sum())
    top_cause = (
        df["FIREGCAUSE_LABEL_NM"].value_counts().idxmax() if fires else "-"
    )

    def card(title, value):
        return pn.pane.HTML(
            f"""
            <div style='background:#fff;border:1px solid #eee;border-radius:10px;
                 padding:14px 18px;box-shadow:0 1px 3px rgba(0,0,0,.06)'>
              <div style='color:#888;font-size:12px;text-transform:uppercase;
                   letter-spacing:.5px'>{title}</div>
              <div style='color:{ACCENT};font-size:26px;font-weight:700'>{value}</div>
            </div>
            """,
            sizing_mode="stretch_width",
        )

    return pn.Row(
        card("Fires", f"{fires:,}"),
        card("Acres burned", f"{acres:,.0f}"),
        card("Large fires (100+ ac)", f"{big:,}"),
        card("Top cause", top_cause),
    )


@pn.depends(year_slider, county_select, cause_select, rank_metric)
def ranking_chart(*_):
    df = filter_df()
    rank = county_rankings(df)
    if rank.empty:
        return pn.pane.Markdown("No data for the current filters.")

    metric = rank_metric.value
    col = {"acres": "acres", "count": "fires", "score": "score"}[metric]
    label = {"acres": "Acres burned", "count": "Number of fires",
             "score": "Priority score (0-100)"}[metric]
    top = rank.sort_values(col, ascending=False).head(15).iloc[::-1]

    fig = px.bar(
        top, x=col, y="county", orientation="h",
        color=col, color_continuous_scale="OrRd",
        labels={col: label, "county": ""},
        hover_data={"fires": True, "acres": ":,.0f", "score": ":.1f"},
    )
    fig.update_layout(
        title=f"Top priority counties by {label.lower()}",
        margin=dict(l=10, r=10, t=50, b=10), height=480,
        coloraxis_showscale=False, plot_bgcolor="white",
    )
    return pn.pane.Plotly(fig, config={"displayModeBar": False})


@pn.depends(year_slider, county_select, cause_select)
def trend_chart(*_):
    df = filter_df()
    if df.empty:
        return pn.pane.Markdown("No data for the current filters.")
    by_year = df.groupby("year").agg(
        fires=("OBJECTID", "count"), acres=("ACRES_BURNED", "sum")
    ).reset_index()

    fig = go.Figure()
    fig.add_bar(x=by_year["year"], y=by_year["acres"], name="Acres burned",
                marker_color=ACCENT, opacity=0.85)
    fig.add_scatter(x=by_year["year"], y=by_year["fires"], name="Fire count",
                    mode="lines+markers", yaxis="y2", line=dict(color="#1f4e79"))
    fig.update_layout(
        title="Acres burned and fire count by year",
        margin=dict(l=10, r=10, t=50, b=10), height=360,
        plot_bgcolor="white", legend=dict(orientation="h", y=1.12),
        yaxis=dict(title="Acres"),
        yaxis2=dict(title="Fires", overlaying="y", side="right", showgrid=False),
    )
    return pn.pane.Plotly(fig, config={"displayModeBar": False})


@pn.depends(year_slider, county_select, cause_select)
def cause_chart(*_):
    df = filter_df()
    if df.empty:
        return pn.pane.Markdown("No data for the current filters.")
    by_cause = (
        df.groupby("FIREGCAUSE_LABEL_NM")
        .agg(fires=("OBJECTID", "count"), acres=("ACRES_BURNED", "sum"))
        .reset_index().sort_values("fires", ascending=False).head(12)
    )
    fig = px.bar(
        by_cause, x="fires", y="FIREGCAUSE_LABEL_NM", orientation="h",
        color="acres", color_continuous_scale="OrRd",
        labels={"fires": "Number of fires", "FIREGCAUSE_LABEL_NM": "",
                "acres": "Acres"},
    )
    fig.update_layout(
        title="Fire causes (bar length = count, color = acres)",
        margin=dict(l=10, r=10, t=50, b=10), height=360,
        yaxis=dict(autorange="reversed"), plot_bgcolor="white",
    )
    return pn.pane.Plotly(fig, config={"displayModeBar": False})


@pn.depends(year_slider, county_select, cause_select)
def fire_map(*_):
    df = filter_df()
    df = df[df["LAT_COORD"].notna() & df["LON_COORD"].notna()]
    # Keep coordinates within a sane Washington bounding box.
    df = df[(df["LAT_COORD"].between(45, 49.5)) & (df["LON_COORD"].between(-125, -116))]

    p = figure(
        x_axis_type="mercator", y_axis_type="mercator",
        height=560, sizing_mode="stretch_width",
        tools="pan,wheel_zoom,box_zoom,reset", active_scroll="wheel_zoom",
        title="Fire locations (circle size = acres burned)",
    )
    p.add_tile("CartoDB Positron")

    if df.empty:
        return pn.pane.Bokeh(p)

    x, y = lonlat_to_mercator(df["LON_COORD"], df["LAT_COORD"])
    size = 4 + 14 * (df["ACRES_BURNED"].clip(upper=20000) ** 0.5) / (20000 ** 0.5)
    source = ColumnDataSource(dict(
        x=x, y=y, size=size,
        acres=df["ACRES_BURNED"], name=df["INCIDENT_NM"],
        county=df["COUNTY_LABEL_NM"], cause=df["FIREGCAUSE_LABEL_NM"],
        year=df["year"],
    ))
    mapper = linear_cmap(
        "acres", palette=["#ffd27f", "#f08c3c", "#c1440e", "#7a1500"],
        low=0, high=float(np.nanpercentile(df["ACRES_BURNED"], 95) or 1),
    )
    r = p.scatter("x", "y", size="size", source=source, color=mapper,
                  alpha=0.65, line_color=None)
    p.add_tools(HoverTool(renderers=[r], tooltips=[
        ("Fire", "@name"), ("Year", "@year"), ("County", "@county"),
        ("Cause", "@cause"), ("Acres", "@acres{0,0.0}"),
    ]))
    return pn.pane.Bokeh(p)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
sidebar = pn.Column(
    pn.pane.Markdown("### Filters"),
    year_slider, county_select, cause_select,
    pn.pane.Markdown("### County ranking"),
    rank_metric,
    pn.pane.Markdown(
        "**Priority score** blends acres burned (45%), fire count (30%), "
        "and recent 5-year acres (25%), each scaled 0-100. Higher = greater "
        "wildfire burden, i.e. where mitigation effort may matter most.",
        styles={"font-size": "12px", "color": "#666"},
    ),
    width=320,
)

main = pn.Column(
    kpi_row,
    pn.Row(ranking_chart, pn.Column(trend_chart, cause_chart)),
    fire_map,
)

template = pn.template.FastListTemplate(
    title="Washington Wildfire Watch",
    header_background=ACCENT,
    sidebar=[sidebar],
    main=[main],
    accent_base_color=ACCENT,
)

template.servable()

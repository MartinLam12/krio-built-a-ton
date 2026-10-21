"""
Washington Wildfire Watch.

A map-first "where to intervene" dashboard built from the public Washington
DNR Fire Statistics 2008-Present point layer.

Run with:
    panel serve app.py --show
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import panel as pn
import plotly.express as px
import plotly.graph_objects as go
from bokeh.models import ColumnDataSource, HoverTool, Range1d, WMTSTileSource
from bokeh.plotting import figure
from bokeh.transform import linear_cmap

import data_source

# ---------------------------------------------------------------------------
# Panorama-inspired visual system
# ---------------------------------------------------------------------------
SIDEBAR_BG = "#203037"
SIDEBAR_DEEP = "#18272d"
MAP_SURROUND = "#dce2e3"
WHITE = "#ffffff"
TEXT_SOFT = "#d7e0e2"
TEAL = "#81d5dc"
RED = "#ff4f5e"
INK = "#182127"
PAPER = "#f7f5ef"
SERIF = "'Georgia', 'Times New Roman', serif"
SANS = "'Helvetica Neue', 'Segoe UI', Arial, sans-serif"

GRADE_COLORS = ["#82bb6a", "#6bc6d7", "#f1dc18", "#ff4f5e"]
GRADE_SCALE = ["#f1dc18", "#e8aa38", "#d9693e", "#ff4f5e", "#8e2032"]

THEME_CSS = f"""
:root {{
  --design-primary-color: {RED};
  --design-background-color: {MAP_SURROUND};
}}
html, body {{
  width: 100%;
  height: 100%;
  margin: 0;
  overflow: hidden;
  background: {MAP_SURROUND};
  font-family: {SANS};
}}
#container, #content, #body-design-provider {{
  height: 100vh !important;
  min-height: 100vh !important;
}}
#header {{ display: none !important; }}
#content {{ margin: 0 !important; top: 0 !important; }}
#sidebar {{
  height: 100vh !important;
  min-height: 100vh !important;
  padding: 0 !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
  background: {SIDEBAR_BG} !important;
  border: 0 !important;
  box-shadow: 4px 0 18px rgba(20, 31, 36, .22);
  z-index: 20;
}}
#sidebar > .nav {{ padding: 0 !important; }}
#sidebar .bk-panel-models-layout-Column {{ max-width: 100% !important; }}
#main {{
  height: 100vh !important;
  min-height: 100vh !important;
  padding: 0 !important;
  margin: 0 !important;
  overflow: hidden !important;
  background: {MAP_SURROUND} !important;
}}
#main .main-margin,
#main .card-margin,
#main .pn-wrapper {{
  width: 100% !important;
  max-width: none !important;
  height: 100vh !important;
  min-height: 100vh !important;
  padding: 0 !important;
  margin: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
}}
#main .fullscreen-button {{ display: none !important; }}
.map-shell {{
  position: relative !important;
  width: 100% !important;
  height: 100vh !important;
  min-height: 100vh !important;
  overflow: hidden !important;
  background: {MAP_SURROUND};
}}
.map-canvas {{
  position: absolute !important;
  inset: 0 !important;
  width: 100% !important;
  height: 100% !important;
}}
.map-overlay {{
  position: absolute !important;
  z-index: 12 !important;
  pointer-events: none;
}}
.map-title-card {{ top: 24px; left: 24px; width: 310px; }}
.map-legend-card {{ bottom: 24px; right: 24px; width: 220px; }}
#sidebar label,
#sidebar .bk-input-group label,
#sidebar .bk-slider-title,
#sidebar .bk-clearfix {{
  color: {WHITE} !important;
}}
#sidebar fast-accordion {{
  --neutral-foreground-rest: {WHITE};
  --design-background-color: {SIDEBAR_DEEP};
}}
.sidebar-pad {{ padding: 0 22px; }}
.brand-block {{ padding: 20px 24px 18px; background: {SIDEBAR_DEEP}; }}
.brand-title {{
  color: {RED};
  font-size: 23px;
  line-height: 1;
  letter-spacing: 1.2px;
  font-weight: 800;
  text-transform: uppercase;
}}
.brand-subtitle {{
  color: #aebec2;
  font-size: 12px;
  letter-spacing: 1.1px;
  text-transform: uppercase;
  margin-top: 5px;
}}
.location-block {{
  padding: 21px 24px 18px;
  text-align: center;
  background: {SIDEBAR_BG};
}}
.location-kicker {{ color: {TEAL}; font-size: 12px; letter-spacing: 1px; }}
.location-name {{ color: {WHITE}; font-size: 26px; margin-top: 8px; }}
.location-subtitle {{
  color: {WHITE}; font-size: 12px; letter-spacing: 1.6px;
  text-transform: uppercase; margin-top: 2px;
}}
.section-label {{
  color: {TEAL}; font-size: 11px; letter-spacing: 1px;
  text-transform: uppercase; margin: 18px 0 9px;
}}
.priority-title {{ color: {WHITE}; font-size: 17px; margin: 22px 0 3px; text-align: center; }}
.priority-subtitle {{ color: #aebec2; font-size: 11px; text-align: center; line-height: 1.45; }}
.summary-grid {{
  display: grid; grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid rgba(255,255,255,.15);
  border-bottom: 1px solid rgba(255,255,255,.15);
  margin-top: 16px;
}}
.summary-cell {{ padding: 12px 5px; text-align: center; border-right: 1px solid rgba(255,255,255,.13); }}
.summary-cell:last-child {{ border-right: 0; }}
.summary-value {{ color: {WHITE}; font-size: 16px; font-weight: 700; }}
.summary-key {{ color: #9fb1b6; font-size: 9px; letter-spacing: .8px; text-transform: uppercase; margin-top: 3px; }}
.priority-card {{
  display: grid; grid-template-columns: 48px 1fr; gap: 14px;
  padding: 17px 6px; border-bottom: 1px solid rgba(0,0,0,.55);
}}
.priority-badge {{
  width: 40px; height: 40px; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; color: #122127;
  font-size: 12px; font-weight: 700; margin-top: 2px;
}}
.priority-county {{ color: {WHITE}; font-size: 14px; font-weight: 700; }}
.priority-copy {{ color: {TEXT_SOFT}; font-size: 12px; line-height: 1.45; margin-top: 4px; }}
.priority-meta {{ color: {TEAL}; font-size: 10px; letter-spacing: .5px; text-transform: uppercase; margin-top: 7px; }}
.sidebar-note {{
  color: #aebec2; font-size: 11px; line-height: 1.5;
  padding: 14px 22px 24px;
}}
"""

pn.extension("plotly", sizing_mode="stretch_width", raw_css=[THEME_CSS])

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
DF = data_source.load()
ALL_YEARS = (int(DF["year"].min()), int(DF["year"].max()))
COUNTIES = ["All counties"] + sorted(DF["COUNTY_LABEL_NM"].unique().tolist())
CAUSES = ["All causes"] + sorted(DF["FIREGCAUSE_LABEL_NM"].unique().tolist())


def lonlat_to_mercator(lon: pd.Series, lat: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Convert longitude/latitude coordinates to web mercator."""
    k = 6378137.0
    x = lon * (k * np.pi / 180.0)
    y = np.log(np.tan((90.0 + lat) * np.pi / 360.0)) * k
    return x, y


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
WHITE_LABEL = """
:host { --design-background-text-color: #ffffff; }
label, .bk-input-group label, .bk-slider-title { color: #ffffff !important; }
"""

year_slider = pn.widgets.IntRangeSlider(
    name="Fire year",
    start=ALL_YEARS[0],
    end=ALL_YEARS[1],
    value=ALL_YEARS,
    step=1,
    stylesheets=[WHITE_LABEL],
)
county_select = pn.widgets.Select(
    name="County",
    options=COUNTIES,
    value="All counties",
    stylesheets=[WHITE_LABEL],
)
cause_select = pn.widgets.Select(
    name="Cause",
    options=CAUSES,
    value="All causes",
    stylesheets=[WHITE_LABEL],
)
rank_metric = pn.widgets.RadioButtonGroup(
    name="Rank counties by",
    options={"Acres": "acres", "Fires": "count", "Priority": "score"},
    value="score",
    sizing_mode="stretch_width",
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
# Priority model
# ---------------------------------------------------------------------------
def county_rankings(df: pd.DataFrame) -> pd.DataFrame:
    """Rank Washington counties by acreage, frequency, and recent activity."""
    if df.empty:
        return pd.DataFrame(columns=["county", "fires", "acres", "recent_acres", "score"])

    recent_cutoff = df["year"].max() - 4
    rank = (
        df.groupby("COUNTY_LABEL_NM")
        .agg(fires=("OBJECTID", "count"), acres=("ACRES_BURNED", "sum"))
        .reset_index()
    )
    recent = (
        df[df["year"] >= recent_cutoff]
        .groupby("COUNTY_LABEL_NM")["ACRES_BURNED"]
        .sum()
        .rename("recent_acres")
    )
    rank = rank.merge(recent, left_on="COUNTY_LABEL_NM", right_index=True, how="left")
    rank["recent_acres"] = rank["recent_acres"].fillna(0.0)
    rank = rank.rename(columns={"COUNTY_LABEL_NM": "county"})

    def norm(series: pd.Series) -> pd.Series:
        span = series.max() - series.min()
        return (series - series.min()) / span if span else series * 0.0

    rank["score"] = (
        0.45 * norm(rank["acres"])
        + 0.30 * norm(rank["fires"])
        + 0.25 * norm(rank["recent_acres"])
    ) * 100.0
    return rank.sort_values("score", ascending=False)


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------
@pn.depends(year_slider, county_select, cause_select)
def fire_map(*_):
    df = filter_df()
    df = df[df["LAT_COORD"].notna() & df["LON_COORD"].notna()]
    df = df[(df["LAT_COORD"].between(45, 49.5)) & (df["LON_COORD"].between(-125, -116))]

    # Washington is only the initial frame. These ranges intentionally have
    # no bounds, allowing users to zoom out and explore the worldwide basemap.
    wa_x, wa_y = lonlat_to_mercator(
        pd.Series([-125.0, -116.0]), pd.Series([45.0, 49.5])
    )
    x_lo, x_hi = float(wa_x.min()), float(wa_x.max())
    y_lo, y_hi = float(wa_y.min()), float(wa_y.max())
    pad_x = (x_hi - x_lo) * 0.04
    pad_y = (y_hi - y_lo) * 0.04

    plot = figure(
        x_axis_type="mercator",
        y_axis_type="mercator",
        x_range=Range1d(x_lo - pad_x, x_hi + pad_x),
        y_range=Range1d(y_lo - pad_y, y_hi + pad_y),
        sizing_mode="stretch_both",
        min_height=650,
        tools="pan,wheel_zoom,box_zoom,reset",
        active_scroll="wheel_zoom",
        toolbar_location="left",
    )
    plot.add_tile(
        WMTSTileSource(
            url="https://tile.openstreetmap.org/{Z}/{X}/{Y}.png",
            attribution="© OpenStreetMap contributors",
        )
    )
    plot.background_fill_color = MAP_SURROUND
    plot.border_fill_color = MAP_SURROUND
    plot.outline_line_color = None
    plot.grid.grid_line_color = None
    plot.axis.visible = False
    plot.toolbar.logo = None
    plot.toolbar.autohide = True

    if not df.empty:
        x, y = lonlat_to_mercator(df["LON_COORD"], df["LAT_COORD"])
        cap = max(float(np.nanpercentile(df["ACRES_BURNED"], 95)), 1.0)
        size = 5 + 15 * np.sqrt(df["ACRES_BURNED"].clip(upper=20000) / 20000)
        source = ColumnDataSource(
            dict(
                x=x,
                y=y,
                size=size,
                acres=df["ACRES_BURNED"],
                name=df["INCIDENT_NM"],
                county=df["COUNTY_LABEL_NM"],
                cause=df["FIREGCAUSE_LABEL_NM"],
                year=df["year"],
            )
        )
        mapper = linear_cmap(
            "acres",
            palette=["#f1dc18", "#e8aa38", "#d9693e", "#ff4f5e", "#8e2032"],
            low=0,
            high=cap,
        )
        renderer = plot.scatter(
            "x",
            "y",
            size="size",
            source=source,
            color=mapper,
            fill_alpha=0.72,
            line_color="#6f1e29",
            line_alpha=0.35,
        )
        plot.add_tools(
            HoverTool(
                renderers=[renderer],
                tooltips=[
                    ("Fire", "@name"),
                    ("Year", "@year"),
                    ("County", "@county"),
                    ("Cause", "@cause"),
                    ("Acres", "@acres{0,0.0}"),
                ],
            )
        )

    return pn.pane.Bokeh(plot, sizing_mode="stretch_both", css_classes=["map-canvas"])


map_title = pn.pane.HTML(
    f"""
    <div style="background:rgba(255,255,255,.94);border:1px solid #64747a;
         box-shadow:0 2px 8px rgba(20,35,40,.2);padding:11px 14px;font-family:{SANS}">
      <div style="color:{INK};font-size:13px;font-weight:700">Washington wildfire activity</div>
      <div style="color:#637279;font-size:11px;margin-top:3px">Drag to pan · scroll to zoom · worldwide basemap</div>
    </div>
    """,
    css_classes=["map-overlay", "map-title-card"],
    width=310,
    height=64,
    sizing_mode="fixed",
)

map_legend = pn.pane.HTML(
    f"""
    <div style="background:rgba(32,48,55,.94);color:white;padding:13px 14px;
         box-shadow:0 2px 8px rgba(20,35,40,.28);font-family:{SANS}">
      <div style="font-size:11px;letter-spacing:.8px;text-transform:uppercase">Acres burned</div>
      <div style="height:9px;margin-top:9px;background:linear-gradient(90deg,
           #f1dc18,#e8aa38,#d9693e,#ff4f5e,#8e2032)"></div>
      <div style="display:flex;justify-content:space-between;color:#d7e0e2;
           font-size:9px;margin-top:5px"><span>Lower</span><span>Higher</span></div>
      <div style="color:#9fb1b6;font-size:9px;line-height:1.4;margin-top:9px">
        Recommendations and fire records are currently Washington-only.
      </div>
    </div>
    """,
    css_classes=["map-overlay", "map-legend-card"],
    width=220,
    height=112,
    sizing_mode="fixed",
)

# ---------------------------------------------------------------------------
# Sidebar content
# ---------------------------------------------------------------------------
@pn.depends(year_slider, county_select, cause_select)
def summary_strip(*_):
    df = filter_df()
    acres = df["ACRES_BURNED"].sum()
    large = int((df["ACRES_BURNED"] >= 100).sum())
    return pn.pane.HTML(
        f"""
        <div class="summary-grid">
          <div class="summary-cell"><div class="summary-value">{len(df):,}</div><div class="summary-key">Fires</div></div>
          <div class="summary-cell"><div class="summary-value">{acres / 1_000_000:.1f}M</div><div class="summary-key">Acres</div></div>
          <div class="summary-cell"><div class="summary-value">{large:,}</div><div class="summary-key">100+ acres</div></div>
        </div>
        """,
        sizing_mode="stretch_width",
    )


@pn.depends(year_slider, county_select, cause_select, rank_metric)
def recommendation_panel(*_):
    df = filter_df()
    rank = county_rankings(df)
    if rank.empty:
        return pn.pane.HTML(
            '<div style="color:white;padding:24px 4px">No Washington records match these filters.</div>'
        )

    metric = {"acres": "acres", "count": "fires", "score": "score"}[rank_metric.value]
    top = rank.sort_values(metric, ascending=False).head(6).reset_index(drop=True)
    cards = []
    badge_colors = [RED, "#f1dc18", "#6bc6d7", "#82bb6a", "#6bc6d7", "#f1dc18"]

    for index, row in top.iterrows():
        recent_share = (row.recent_acres / row.acres * 100) if row.acres else 0
        if row.score >= 66:
            level = "Highest current priority"
        elif row.score >= 33:
            level = "Elevated priority"
        else:
            level = "Monitor"
        cards.append(
            f"""
            <div class="priority-card">
              <div class="priority-badge" style="background:{badge_colors[index]}">{index + 1:02d}</div>
              <div>
                <div class="priority-county">{row.county} County</div>
                <div class="priority-copy">{int(row.fires):,} fires burned {row.acres:,.0f} acres; {recent_share:.0f}% of acreage occurred in the latest five years shown.</div>
                <div class="priority-meta">{level} · score {row.score:.0f}</div>
              </div>
            </div>
            """
        )

    return pn.pane.HTML("".join(cards), sizing_mode="stretch_width")


def _editorial(figure_obj):
    figure_obj.update_layout(
        paper_bgcolor=SIDEBAR_BG,
        plot_bgcolor=SIDEBAR_BG,
        font=dict(family="Helvetica Neue, Arial, sans-serif", color=WHITE, size=10),
        title_font=dict(color=WHITE, size=14),
        margin=dict(l=8, r=8, t=42, b=20),
        xaxis=dict(gridcolor="#3b4c52", zerolinecolor="#3b4c52"),
        yaxis=dict(gridcolor="#3b4c52", zerolinecolor="#3b4c52"),
        legend=dict(font=dict(color=WHITE)),
    )
    return figure_obj


@pn.depends(year_slider, county_select, cause_select, rank_metric)
def ranking_chart(*_):
    rank = county_rankings(filter_df())
    if rank.empty:
        return pn.pane.Markdown("No data for the current filters.")
    metric = {"acres": "acres", "count": "fires", "score": "score"}[rank_metric.value]
    label = {"acres": "Acres burned", "count": "Number of fires", "score": "Priority score"}[rank_metric.value]
    top = rank.sort_values(metric, ascending=False).head(10).iloc[::-1]
    chart = px.bar(
        top,
        x=metric,
        y="county",
        orientation="h",
        color=metric,
        color_continuous_scale=GRADE_SCALE,
        labels={metric: label, "county": ""},
    )
    chart.update_layout(title="County ranking", height=380, coloraxis_showscale=False)
    return pn.pane.Plotly(_editorial(chart), config={"displayModeBar": False})


@pn.depends(year_slider, county_select, cause_select)
def trend_chart(*_):
    df = filter_df()
    if df.empty:
        return pn.pane.Markdown("No data for the current filters.")
    by_year = df.groupby("year").agg(fires=("OBJECTID", "count"), acres=("ACRES_BURNED", "sum")).reset_index()
    chart = go.Figure()
    chart.add_bar(x=by_year["year"], y=by_year["acres"], name="Acres", marker_color=RED)
    chart.add_scatter(x=by_year["year"], y=by_year["fires"], name="Fires", mode="lines", yaxis="y2", line=dict(color=TEAL))
    chart.update_layout(
        title="Annual activity",
        height=330,
        yaxis2=dict(overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.12),
    )
    return pn.pane.Plotly(_editorial(chart), config={"displayModeBar": False})


brand = pn.pane.HTML(
    """
    <div class="brand-block">
      <div class="brand-title">Mapping Wildfire</div>
      <div class="brand-subtitle">Risk and activity in Washington</div>
    </div>
    <div class="location-block">
      <div class="location-kicker">◉&nbsp; CURRENT COVERAGE</div>
      <div class="location-name">Washington</div>
      <div class="location-subtitle">United States</div>
    </div>
    """,
    sizing_mode="stretch_width",
)

filters = pn.Column(
    pn.pane.HTML('<div class="section-label">Explore the records</div>'),
    year_slider,
    county_select,
    cause_select,
    rank_metric,
    css_classes=["sidebar-pad"],
    sizing_mode="stretch_width",
)

priority_intro = pn.pane.HTML(
    """
    <div class="sidebar-pad">
      <div class="priority-title">Selections from the priority model</div>
      <div class="priority-subtitle">Ranked from Washington DNR fire frequency, acreage, and recent activity.</div>
    </div>
    """,
    sizing_mode="stretch_width",
)

supporting_data = pn.Accordion(
    ("COUNTY RANKING", ranking_chart),
    ("ANNUAL ACTIVITY", trend_chart),
    active=[],
    sizing_mode="stretch_width",
    margin=(10, 16, 0, 16),
)

sidebar = pn.Column(
    brand,
    filters,
    summary_strip,
    priority_intro,
    pn.Column(recommendation_panel, css_classes=["sidebar-pad"], sizing_mode="stretch_width"),
    supporting_data,
    pn.pane.HTML(
        """
        <div class="sidebar-note">
          Priority scores identify wildfire burden, not treatment suitability. No recommendations are shown outside Washington because the source dataset has no coverage there.
          <br><br>Source: Washington State Department of Natural Resources. Locations are approximate.
        </div>
        """
    ),
    sizing_mode="stretch_width",
)

map_shell = pn.Column(
    pn.panel(fire_map, sizing_mode="stretch_both"),
    map_title,
    map_legend,
    css_classes=["map-shell"],
    sizing_mode="stretch_both",
)

template = pn.template.FastListTemplate(
    title="Mapping Wildfire | Washington",
    sidebar=[sidebar],
    main=[map_shell],
    sidebar_width=475,
    collapsed_sidebar=False,
    main_layout=None,
    main_max_width="",
    theme_toggle=False,
    background_color=MAP_SURROUND,
    accent_base_color=RED,
    header_background=SIDEBAR_DEEP,
)

template.servable()

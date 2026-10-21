"""
Martin's widget -- county wildfire burden and annual activity graphs.

This adapts the strongest graph concepts from Martin's standalone
`origin/martin` dashboard to the shared team widget contract. It intentionally
uses `load_fire_data()` rather than Martin's separate downloader/cache, and it
returns one named Panel component instead of creating a competing app template.

The county priority score follows Martin's documented model:
  * 45% normalized historical acres burned
  * 30% normalized fire-incident count
  * 25% normalized acres burned in the latest five years of the selected data

The score ranks historical burden for planning; it is not a treatment
recommendation or forecast.
"""
from __future__ import annotations

import html

import pandas as pd
import panel as pn

from data_access import data_available, load_fire_data

try:
    import hvplot.pandas  # noqa: F401 - registers the DataFrame accessor

    CHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - teammate environment fallback
    CHARTS_AVAILABLE = False

TITLE = "County Wildfire Priority & Trends"

PRIORITY_WEIGHTS = {
    "acres": 0.45,
    "fires": 0.30,
    "recent_acres": 0.25,
}


def _normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize a metric, returning zeros when it has no range."""
    clean = pd.to_numeric(series, errors="coerce").fillna(0.0)
    span = clean.max() - clean.min()
    return (clean - clean.min()) / span if span else clean * 0.0


def compute_county_rankings(data: pd.DataFrame) -> pd.DataFrame:
    """Compute Martin's transparent county-level historical burden score."""
    required = {"COUNTY_LABEL_NM", "ACRES_BURNED", "DSCVR_YEAR"}
    if data.empty or not required.issubset(data.columns):
        return pd.DataFrame(
            columns=["county", "fires", "acres", "recent_acres", "score"]
        )

    frame = data.dropna(subset=["COUNTY_LABEL_NM", "DSCVR_YEAR"]).copy()
    if frame.empty:
        return pd.DataFrame(
            columns=["county", "fires", "acres", "recent_acres", "score"]
        )

    frame["ACRES_BURNED"] = pd.to_numeric(
        frame["ACRES_BURNED"], errors="coerce"
    ).fillna(0.0).clip(lower=0)
    latest_year = int(frame["DSCVR_YEAR"].max())
    recent_cutoff = latest_year - 4

    ranking = (
        frame.groupby("COUNTY_LABEL_NM", observed=True)
        .agg(fires=("COUNTY_LABEL_NM", "size"), acres=("ACRES_BURNED", "sum"))
        .reset_index()
        .rename(columns={"COUNTY_LABEL_NM": "county"})
    )
    recent = (
        frame[frame["DSCVR_YEAR"] >= recent_cutoff]
        .groupby("COUNTY_LABEL_NM", observed=True)["ACRES_BURNED"]
        .sum()
        .rename("recent_acres")
    )
    ranking = ranking.merge(
        recent,
        left_on="county",
        right_index=True,
        how="left",
    )
    ranking["recent_acres"] = ranking["recent_acres"].fillna(0.0)
    ranking["score"] = 100 * (
        PRIORITY_WEIGHTS["acres"] * _normalize(ranking["acres"])
        + PRIORITY_WEIGHTS["fires"] * _normalize(ranking["fires"])
        + PRIORITY_WEIGHTS["recent_acres"]
        * _normalize(ranking["recent_acres"])
    )
    return ranking.sort_values("score", ascending=False).reset_index(drop=True)


def _filter_data(
    data: pd.DataFrame,
    year_range: tuple[int, int],
    causes: list[str],
) -> pd.DataFrame:
    """Apply widget filters without modifying the shared cached DataFrame."""
    low, high = year_range
    filtered = data[
        (data["DSCVR_YEAR"] >= low) & (data["DSCVR_YEAR"] <= high)
    ]
    if causes:
        filtered = filtered[filtered["FIREGCAUSE_LABEL_NM"].isin(causes)]
    return filtered.copy()


def _summary_html(ranking: pd.DataFrame, record_count: int) -> str:
    """Render a compact summary above Martin's graphs."""
    if ranking.empty:
        top_county = "No ranked county"
        score = "—"
        acres = "—"
    else:
        top = ranking.iloc[0]
        top_county = html.escape(str(top["county"]))
        score = f"{top['score']:.1f} / 100"
        acres = f"{top['acres']:,.0f} acres"

    cards = (
        ("TOP PRIORITY COUNTY", top_county, score, "#8F2430"),
        ("HISTORICAL BURDEN", acres, "Top-ranked county", "#C75B35"),
        ("FILTERED RECORDS", f"{record_count:,}", "Used in this analysis", "#31566D"),
    )
    content = "".join(
        f"<div style='background:#FFFFFF;border:1px solid #D6E0E6;"
        f"border-top:3px solid {accent};border-radius:3px;padding:9px 11px'>"
        f"<div style='font-size:9px;font-weight:700;letter-spacing:.1em;color:#607584'>"
        f"{label}</div><div style='font-size:16px;font-weight:700;color:#172B3A;"
        f"margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
        f"{value}</div><div style='font-size:10px;color:#71818D'>{detail}</div></div>"
        for label, value, detail, accent in cards
    )
    return (
        "<div style='display:grid;grid-template-columns:repeat(3,minmax(0,1fr));"
        f"gap:7px'>{content}</div>"
    )


def create_panel() -> pn.viewable.Viewable:
    """Return Martin's graphs as one self-contained team widget."""
    if not data_available():
        return pn.Column(
            pn.pane.Alert(
                "Fire data is unavailable. Run `python fire_data_pull.py` first.",
                alert_type="warning",
            ),
            name=TITLE,
        )

    if not CHARTS_AVAILABLE:
        return pn.Column(
            pn.pane.Alert(
                "Martin's graphs require `hvplot`. Install it in the project "
                "environment and restart the dashboard.",
                alert_type="warning",
            ),
            name=TITLE,
        )

    data = load_fire_data()
    required = {
        "COUNTY_LABEL_NM",
        "FIREGCAUSE_LABEL_NM",
        "ACRES_BURNED",
        "DSCVR_YEAR",
    }
    if data.empty or not required.issubset(data.columns):
        return pn.Column(
            pn.pane.Alert(
                "The fire dataset is empty or missing fields required by this graph.",
                alert_type="warning",
            ),
            name=TITLE,
        )

    years = sorted(int(year) for year in data["DSCVR_YEAR"].dropna().unique())
    if not years:
        return pn.Column(
            pn.pane.Alert("No dated fire records are available.", alert_type="warning"),
            name=TITLE,
        )

    header = pn.pane.HTML(
        """
        <div style="background:#172B3A;border-left:5px solid #C75B35;border-radius:3px;
                    padding:13px 15px;color:#FFFFFF;font-family:Arial,sans-serif">
          <div style="font-size:9px;font-weight:700;letter-spacing:.15em;color:#AFC0CB">
            WASHINGTON MITIGATION PLANNING · COUNTY ANALYSIS
          </div>
          <div style="font-size:19px;font-weight:700;margin-top:4px">
            Historical Burden & Activity
          </div>
          <div style="font-size:11px;color:#D2DDE3;margin-top:4px">
            County priority ranking and year-over-year wildfire trends
          </div>
        </div>
        """,
        sizing_mode="stretch_width",
    )

    year_range = pn.widgets.IntRangeSlider(
        name="Analysis period",
        start=years[0],
        end=years[-1],
        value=(years[0], years[-1]),
        step=1,
    )
    cause_select = pn.widgets.MultiChoice(
        name="General cause",
        options=sorted(data["FIREGCAUSE_LABEL_NM"].dropna().unique().tolist()),
        placeholder="All causes",
    )
    ranking_metric = pn.widgets.Select(
        name="County ranking metric",
        options={
            "Priority score": "score",
            "Acres burned": "acres",
            "Fire incidents": "fires",
        },
        value="score",
    )
    top_n = pn.widgets.IntSlider(name="Counties shown", start=5, end=15, value=10)

    controls = pn.Column(
        pn.pane.HTML(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
            "color:#405A6B'>GRAPH CONTROLS</div>"
        ),
        pn.GridBox(
            year_range,
            cause_select,
            ranking_metric,
            top_n,
            ncols=2,
            sizing_mode="stretch_width",
        ),
        styles={
            "background": "#F4F7F9",
            "border": "1px solid #D6E0E6",
            "border-radius": "3px",
            "padding": "10px",
        },
        sizing_mode="stretch_width",
    )

    @pn.depends(year_range, cause_select, ranking_metric, top_n)
    def county_ranking(yr_range, causes, metric, count):
        filtered = _filter_data(data, yr_range, causes)
        ranking = compute_county_rankings(filtered)
        if ranking.empty:
            return pn.pane.Alert(
                "No county records match the selected filters.", alert_type="info"
            )

        metric_labels = {
            "score": "Priority score (0–100)",
            "acres": "Acres burned",
            "fires": "Fire incidents",
        }
        chart_data = (
            ranking.nlargest(count, metric)
            .sort_values(metric)
            .assign(
                score=lambda frame: frame["score"].round(1),
                acres=lambda frame: frame["acres"].round(0),
                recent_acres=lambda frame: frame["recent_acres"].round(0),
            )
        )
        chart = chart_data.hvplot.bar(
            x="county",
            y=metric,
            color="#C75B35",
            height=390,
            responsive=True,
            xlabel="",
            ylabel=metric_labels[metric],
            title=f"Top {len(chart_data)} counties by {metric_labels[metric].lower()}",
            hover_cols=["fires", "acres", "recent_acres", "score"],
            grid=True,
        ).opts(toolbar="above", invert_axes=True)
        return pn.Column(
            pn.pane.HTML(
                _summary_html(ranking, len(filtered)), sizing_mode="stretch_width"
            ),
            chart,
            sizing_mode="stretch_width",
        )

    @pn.depends(year_range, cause_select)
    def annual_activity(yr_range, causes):
        filtered = _filter_data(data, yr_range, causes)
        if filtered.empty:
            return pn.pane.Alert(
                "No annual records match the selected filters.", alert_type="info"
            )

        annual = (
            filtered.groupby("DSCVR_YEAR", observed=True)
            .agg(fires=("DSCVR_YEAR", "size"), acres=("ACRES_BURNED", "sum"))
            .reset_index()
            .sort_values("DSCVR_YEAR")
        )
        annual["Year"] = annual["DSCVR_YEAR"].astype(int).astype(str)
        acres_chart = annual.hvplot.bar(
            x="Year",
            y="acres",
            color="#8F2430",
            height=245,
            responsive=True,
            xlabel="",
            ylabel="Acres burned",
            title="Annual acres burned",
            rot=45,
            grid=True,
            hover_cols=["fires"],
        ).opts(toolbar="above")
        fires_chart = annual.hvplot.line(
            x="Year",
            y="fires",
            color="#31566D",
            line_width=2.5,
            height=225,
            responsive=True,
            xlabel="Discovery year",
            ylabel="Fire incidents",
            title="Annual fire count",
            rot=45,
            grid=True,
            hover_cols=["acres"],
        ).opts(toolbar="above")
        return pn.Column(acres_chart, fires_chart, sizing_mode="stretch_width")

    tabs = pn.Tabs(
        ("COUNTY PRIORITY", county_ranking),
        ("ANNUAL ACTIVITY", annual_activity),
        dynamic=True,
        sizing_mode="stretch_width",
    )
    methodology = pn.pane.HTML(
        """
        <div style="background:#F7F9FA;border:1px solid #D6E0E6;border-left:3px solid #C75B35;
                    border-radius:3px;padding:9px 11px;color:#526575;font:10px Arial,sans-serif;
                    line-height:1.45">
          <b style="color:#263B4A">METHOD.</b> County priority combines total historical acres (45%),
          incident count (30%), and acres in the latest five years represented by the selected data (25%).
          Values are normalized within the filtered view. This ranks historical burden; it is not a
          treatment recommendation or live wildfire forecast.
        </div>
        """,
        sizing_mode="stretch_width",
    )

    return pn.Column(
        header,
        controls,
        tabs,
        methodology,
        name=TITLE,
        sizing_mode="stretch_width",
        styles={"gap": "10px"},
    )

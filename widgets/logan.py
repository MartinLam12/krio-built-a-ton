"""
Logan's widget -- Drought-Based Wildfire Risk Predictor.

A DNR fire official's hardest question is forward-looking: *given current
conditions, how bad is this fire season likely to be?* Drought is the best
cheap leading indicator we have. This widget joins two public datasets:

  * the DNR fire record (2008-present), and
  * the U.S. Drought Monitor's weekly Drought Severity & Coverage Index (DSCI,
    0-500) for Washington,

and turns them into a simple, defensible predictor. We group historical months
into drought bands and show the average number of fires that actually occurred
in each band -- so the official can read "when the state is in Severe drought,
expect ~N fires that month." We then take the latest DSCI reading and place
this season on that same scale.

This is a historical-relationship predictor, not a trained model: it says what
has happened before at a given drought level, which is exactly the kind of
planning signal that holds up in a briefing. Everything stays inside this
module and reads shared data through `data_access`.
"""

from __future__ import annotations

import pandas as pd
import panel as pn

from data_access import (
    data_available,
    drought_available,
    load_drought_data,
    load_fire_data,
)

try:
    import hvplot.pandas  # noqa: F401
    _HVPLOT = True
except Exception:  # noqa: BLE001
    _HVPLOT = False

TITLE = "Drought-Based Wildfire Risk Predictor"

# DSCI is 0-500. These bands follow the U.S. Drought Monitor's own framing:
# 0 = no drought coverage, rising through moderate/severe/extreme/exceptional.
# We collapse to four planning bands that are easy to brief.
_DROUGHT_BANDS = [
    (0, 50, "None / Abnormally dry"),
    (50, 150, "Moderate drought"),
    (150, 300, "Severe drought"),
    (300, 501, "Extreme drought"),
]
_BAND_ORDER = [b[2] for b in _DROUGHT_BANDS]
_BAND_COLOR = {
    "None / Abnormally dry": "#fbbf24",
    "Moderate drought": "#fb923c",
    "Severe drought": "#ef4444",
    "Extreme drought": "#991b1b",
}


def _band_for(dsci: float) -> str | None:
    """Map a DSCI value to a planning band label."""
    if dsci is None or pd.isna(dsci):
        return None
    for lo, hi, label in _DROUGHT_BANDS:
        if lo <= dsci < hi:
            return label
    return _BAND_ORDER[-1]


def _fires_by_month(fires: pd.DataFrame) -> pd.DataFrame:
    """Monthly fire counts keyed by year-month period, from DSCVR_DATE."""
    if "DSCVR_DATE" not in fires.columns:
        return pd.DataFrame(columns=["YM", "Fires"])
    d = fires.dropna(subset=["DSCVR_DATE"]).copy()
    d["YM"] = d["DSCVR_DATE"].dt.to_period("M")
    return d.groupby("YM").size().rename("Fires").reset_index()


def _drought_by_month(drought: pd.DataFrame) -> pd.DataFrame:
    """Monthly mean DSCI keyed by year-month period, from the weekly series."""
    if "DATE" not in drought.columns or "DSCI" not in drought.columns:
        return pd.DataFrame(columns=["YM", "DSCI"])
    d = drought.dropna(subset=["DATE", "DSCI"]).copy()
    d["YM"] = d["DATE"].dt.to_period("M")
    return d.groupby("YM")["DSCI"].mean().rename("DSCI").reset_index()


def _joined_monthly(fires: pd.DataFrame, drought: pd.DataFrame) -> pd.DataFrame:
    """Inner-join monthly fires and monthly DSCI; add band + plain month ts."""
    fm = _fires_by_month(fires)
    dm = _drought_by_month(drought)
    if fm.empty or dm.empty:
        return pd.DataFrame(columns=["YM", "Fires", "DSCI", "Band", "Date"])
    joined = fm.merge(dm, on="YM", how="inner")
    joined["Band"] = joined["DSCI"].map(_band_for)
    joined["Date"] = joined["YM"].dt.to_timestamp()
    return joined


def _missing_card(message: str) -> pn.viewable.Viewable:
    return pn.Column(
        f"## {TITLE}",
        pn.pane.Alert(message, alert_type="warning"),
        name=TITLE,
    )


def create_panel() -> pn.viewable.Viewable:
    """Return Logan's Drought-Based Wildfire Risk Predictor."""
    if not data_available():
        return _missing_card(
            "Fire data not found. Run `python fire_data_pull.py` first."
        )
    if not drought_available():
        return _missing_card(
            "Drought data not found. Run `python drought_data_pull.py` to pull "
            "the U.S. Drought Monitor DSCI series for Washington."
        )

    fires = load_fire_data()
    drought = load_drought_data()
    if fires.empty or drought.empty:
        return _missing_card("One of the data files is empty.")

    monthly = _joined_monthly(fires, drought)
    if monthly.empty:
        return _missing_card(
            "Could not align the fire and drought series by month."
        )

    # ---- the predictor: average fires per month within each drought band ----
    band_stats = (
        monthly.groupby("Band")
        .agg(AvgFires=("Fires", "mean"),
             Months=("Fires", "size"),
             MaxFires=("Fires", "max"))
        .reindex(_BAND_ORDER)
        .dropna(how="all")
        .reset_index()
    )
    band_stats["AvgFires"] = band_stats["AvgFires"].round(0)

    # ---- current signal: latest weekly DSCI -> band -> expected fires -------
    latest = drought.dropna(subset=["DATE", "DSCI"]).sort_values("DATE").iloc[-1]
    latest_dsci = float(latest["DSCI"])
    latest_band = _band_for(latest_dsci)
    latest_date = pd.Timestamp(latest["DATE"]).date()

    expected = band_stats.loc[band_stats["Band"] == latest_band, "AvgFires"]
    expected_fires = int(expected.iloc[0]) if not expected.empty else None

    # ------------------------------------------------------------- KPI cards
    def card(title: str, value: str, sub: str, color: str = "#b91c1c") -> pn.pane.HTML:
        return pn.pane.HTML(
            f"""
            <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
                        padding:14px 18px;box-shadow:0 1px 2px rgba(0,0,0,.05);">
              <div style="font-size:11px;color:#6b7280;text-transform:uppercase;
                          letter-spacing:.05em;">{title}</div>
              <div style="font-size:24px;font-weight:700;color:{color};
                          margin-top:4px;">{value}</div>
              <div style="font-size:11px;color:#9ca3af;margin-top:2px;">{sub}</div>
            </div>
            """,
            sizing_mode="stretch_width",
        )

    kpis = pn.Row(
        card("Latest WA drought (DSCI)", f"{latest_dsci:.0f}",
             f"of 500 · week of {latest_date}"),
        card("Current drought band", latest_band or "n/a",
             "U.S. Drought Monitor", _BAND_COLOR.get(latest_band, "#b91c1c")),
        card("Expected fires / month",
             f"~{expected_fires:,}" if expected_fires is not None else "n/a",
             "historical avg at this band"),
        sizing_mode="stretch_width",
    )

    # ---------------------------------------------- predictor bar: fires/band
    if _HVPLOT and not band_stats.empty:
        predictor = band_stats.hvplot.bar(
            x="Band", y="AvgFires",
            title="Historical avg fires per month, by drought band",
            color="#ef4444", height=300, rot=20,
        )
    else:
        predictor = pn.widgets.Tabulator(band_stats, disabled=True, height=240)

    # ------------------------------------- relationship: DSCI vs fires scatter
    if _HVPLOT:
        relationship = monthly.hvplot.scatter(
            x="DSCI", y="Fires",
            title="Monthly fires vs. drought severity (each point = one month)",
            color="#f97316", height=300, alpha=0.6,
            hover_cols=["Date"],
        )
    else:
        relationship = pn.pane.Markdown(
            "_Install hvplot to see the drought-vs-fire scatter._"
        )

    corr = monthly["DSCI"].corr(monthly["Fires"])
    corr_note = pn.pane.Markdown(
        f"**Read:** across {len(monthly):,} months since 2008, monthly fire "
        f"counts and drought severity move together "
        f"(correlation r = {corr:.2f}). Higher drought bands have historically "
        f"meant more fires, which is why the current band is a useful heads-up "
        f"for the season ahead."
    )

    header = pn.pane.Markdown(
        "**How bad is this season likely to be?** This pairs Washington's "
        "weekly drought index with the fire record to turn current conditions "
        "into an expected fire load."
    )

    return pn.Column(
        header,
        kpis,
        predictor,
        relationship,
        corr_note,
        name=TITLE,
        sizing_mode="stretch_width",
    )

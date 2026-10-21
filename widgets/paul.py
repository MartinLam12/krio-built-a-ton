"""
Paul's widget -- interactive WA wildfire recurrence and incident-density map.

The map combines individual WA DNR fire records with an approximate spatial
recurrence model. Historical incidents are grouped into fixed geographic cells;
areas with more repeated incidents render as larger bubbles and receive a
higher relative recurrence index. This is a historical screening indicator,
not a live ignition/re-ignition forecast. Weather, fuel moisture, wind, current
containment status, and other operational inputs are required for forecasting.

INTEGRATION FOR TEAMMATES
-------------------------
Other widgets (for example Logan's weather system) can add Folium layers to the
same map without changing this module:

    from widgets.paul import build_fire_map, make_weather_layer

    weather = make_weather_layer(weather_points, name="Current weather")
    map_ = build_fire_map(fire_df, overlays=[weather])

`weather_points` accepts dictionaries with `lat`, `lon`, and optional `label`
and `value` keys. Any object exposing `.add_to(map)` can be supplied through
`overlays`.

Per AGENTS.md, this module loads data only through `load_fire_data()` and
exposes one `create_panel()` entry point for the team dashboard.
"""
from __future__ import annotations

import html
import math
from typing import Iterable, Sequence

import panel as pn

from data_access import (
    data_available,
    drought_available,
    load_drought_data,
    load_fire_data,
)

# Folium (Leaflet) is optional at app-import time so one missing dependency
# cannot take down the other teammates' widgets.
try:
    import folium
    from folium.plugins import Fullscreen, MarkerCluster

    FOLIUM_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on teammates' machines
    folium = None
    Fullscreen = None
    MarkerCluster = None
    FOLIUM_AVAILABLE = False

TITLE = "WA Wildfire Recurrence Monitor"

# Washington geographic bounds used to reject invalid coordinates and frame the
# map. Recurrence bubbles use approximate square cells, not administrative
# boundaries.
WA_LAT_MIN, WA_LAT_MAX = 45.5, 49.05
WA_LON_MIN, WA_LON_MAX = -124.85, -116.90
WA_CENTER = [47.4, -120.5]
DEFAULT_CELL_KM = 20
DEFAULT_MAX_HOTSPOTS = 80

# Free, no-key basemaps.
ESRI_SATELLITE = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_TERRAIN = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Terrain_Base/MapServer/tile/{z}/{y}/{x}"
)

# Muted, government-style risk palette.
RISK_BANDS = (
    (80, "Very high", "#8F2430"),
    (60, "High", "#C54F2D"),
    (40, "Elevated", "#D89A2B"),
    (0, "Watch", "#3E6B82"),
)


def _clean_text(value, fallback: str = "Unknown") -> str:
    """Return an HTML-safe display value, treating null/NaN as missing."""
    if value is None:
        return fallback
    try:
        if value != value:  # NaN
            return fallback
    except Exception:
        pass
    text = str(value).strip()
    return html.escape(text) if text else fallback


def _series_mode(series, fallback: str = "Unknown") -> str:
    """Return the most common non-null string in a pandas Series."""
    values = series.dropna()
    if values.empty:
        return fallback
    modes = values.astype(str).mode()
    return str(modes.iloc[0]) if not modes.empty else str(values.iloc[0])


def _fire_color(acres: float) -> str:
    """Color an individual incident by acres burned."""
    if acres >= 1000:
        return "#7F1D1D"
    if acres >= 100:
        return "#B91C1C"
    if acres >= 10:
        return "#E85D34"
    if acres >= 1:
        return "#D89A2B"
    return "#5B7F67"


def _fire_radius(acres: float) -> float:
    """Size an individual incident marker by acres burned."""
    if acres >= 1000:
        return 11
    if acres >= 100:
        return 8
    if acres >= 10:
        return 6
    if acres >= 1:
        return 4.5
    return 3.5


def _risk_band(score: int) -> tuple[str, str]:
    """Return the label and color for a relative recurrence score."""
    for threshold, label, color in RISK_BANDS:
        if score >= threshold:
            return label, color
    return "Watch", "#3E6B82"


def _frequency_label(rate: float) -> str:
    """Format an estimated historical incident frequency for humans."""
    if rate >= 10:
        return f"{rate:,.0f} recorded incidents / year"
    if rate >= 1:
        return f"{rate:,.1f} recorded incidents / year"
    if rate > 0:
        interval = 1 / rate
        return f"about 1 recorded incident / {interval:,.1f} years"
    return "No recurrence estimate"


def _drought_band(dsci: float) -> str:
    """Present Logan's statewide DSCI using the same broad severity bands."""
    if dsci < 50:
        return "None / abnormally dry"
    if dsci < 150:
        return "Moderate drought"
    if dsci < 300:
        return "Severe drought"
    return "Extreme drought"


def _latest_drought_context() -> dict | None:
    """Read the latest statewide DSCI from Logan's shared data source."""
    if not drought_available():
        return None
    try:
        drought = load_drought_data().dropna(subset=["DATE", "DSCI"])
        if drought.empty:
            return None
        latest = drought.sort_values("DATE").iloc[-1]
        dsci = float(latest["DSCI"])
        date = latest["DATE"]
        return {
            "dsci": dsci,
            "band": _drought_band(dsci),
            "date": date,
            "date_label": date.strftime("%b %d, %Y"),
        }
    except Exception:  # optional teammate data must never block the map
        # Logan's card remains the source of truth; malformed or unreadable
        # drought context must never prevent Paul's map from rendering.
        return None


def to_wa_bounds(df):
    """Return a copy of rows with usable coordinates inside Washington."""
    required = {"LAT_COORD", "LON_COORD"}
    if df.empty or not required.issubset(df.columns):
        return df.iloc[0:0].copy()
    data = df.dropna(subset=["LAT_COORD", "LON_COORD"])
    return data[
        data["LAT_COORD"].between(WA_LAT_MIN, WA_LAT_MAX)
        & data["LON_COORD"].between(WA_LON_MIN, WA_LON_MAX)
    ].copy()


def make_weather_layer(
    points: Iterable[dict],
    *,
    name: str = "Weather",
    color: str = "#2563EB",
) -> folium.FeatureGroup:
    """Convert plain weather readings into a toggleable Folium layer."""
    if not FOLIUM_AVAILABLE:
        raise RuntimeError("Folium is required to build a weather layer.")

    group = folium.FeatureGroup(name=name, show=True)
    for point in points:
        lat, lon = point.get("lat"), point.get("lon")
        if lat is None or lon is None:
            continue
        label = _clean_text(point.get("label"), "Weather observation")
        value = _clean_text(point.get("value"), "")
        tooltip = label if not value else f"{label} · {value}"
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.45,
            tooltip=folium.Tooltip(tooltip, sticky=False),
        ).add_to(group)
    return group


def compute_recurrence_hotspots(
    df,
    *,
    cell_km: int = DEFAULT_CELL_KM,
    observation_years: int | None = None,
    min_incidents: int = 3,
    max_hotspots: int = DEFAULT_MAX_HOTSPOTS,
) -> list[dict]:
    """
    Aggregate incidents into approximate geographic cells.

    The relative recurrence index is the log-scaled incident concentration
    compared with the densest cell in the filtered view. That guarantees the
    behavior shown on the map: more clustered records always produce a larger
    bubble and an equal-or-higher recurrence index. Active-year persistence and
    the latest recorded year are reported separately in the hover details.

    The index ranks historical recurrence within the filtered view; it is not
    a probability or an operational wildfire forecast.
    """
    data = to_wa_bounds(df)
    if data.empty:
        return []

    # Degree widths chosen from the requested cell size at WA's midpoint.
    lat_step = max(cell_km / 111.0, 0.01)
    lon_scale = 111.0 * math.cos(math.radians(WA_CENTER[0]))
    lon_step = max(cell_km / lon_scale, 0.01)

    data["_cell_y"] = ((data["LAT_COORD"] - WA_LAT_MIN) / lat_step).astype(int)
    data["_cell_x"] = ((data["LON_COORD"] - WA_LON_MIN) / lon_step).astype(int)

    years = data.get("DSCVR_YEAR")
    valid_years = years.dropna() if years is not None else []
    if observation_years is None:
        if len(valid_years):
            observation_years = max(1, int(valid_years.max() - valid_years.min() + 1))
        else:
            observation_years = 1
    observation_years = max(1, int(observation_years))

    hotspots = []
    for _, group in data.groupby(["_cell_y", "_cell_x"], sort=False):
        incident_count = len(group)
        if incident_count < min_incidents:
            continue

        group_years = group["DSCVR_YEAR"].dropna() if "DSCVR_YEAR" in group else []
        active_years = int(group_years.nunique()) if len(group_years) else 0
        latest_year = int(group_years.max()) if len(group_years) else None
        county = (
            _series_mode(group["COUNTY_LABEL_NM"])
            if "COUNTY_LABEL_NM" in group
            else "Unknown"
        )
        region = (
            _series_mode(group["REGION_NAME"])
            if "REGION_NAME" in group
            else "Unknown"
        )
        acres = (
            float(group["ACRES_BURNED"].fillna(0).sum())
            if "ACRES_BURNED" in group
            else 0.0
        )
        hotspots.append(
            {
                "lat": float(group["LAT_COORD"].mean()),
                "lon": float(group["LON_COORD"].mean()),
                "count": incident_count,
                "active_years": active_years,
                "observation_years": observation_years,
                "latest_year": latest_year,
                "frequency": incident_count / observation_years,
                "acres": acres,
                "county": county,
                "region": region,
                "cell_km": cell_km,
            }
        )

    if not hotspots:
        return []

    max_count = max(item["count"] for item in hotspots)
    max_log_count = math.log1p(max_count) or 1.0
    for item in hotspots:
        # Both index and radius are monotonic with incident count: a denser
        # cell can never appear smaller or lower-risk than a less-dense cell.
        density = math.log1p(item["count"]) / max_log_count
        score = round(100 * density)
        label, color = _risk_band(score)
        item.update(
            {
                "score": score,
                "label": label,
                "color": color,
                "radius": 6 + 19 * math.sqrt(item["count"] / max_count),
            }
        )

    hotspots.sort(key=lambda item: (item["score"], item["count"]), reverse=True)
    return hotspots[:max_hotspots]


def build_recurrence_layer(
    hotspots: Sequence[dict],
    *,
    name: str = "Historical recurrence index",
) -> folium.FeatureGroup | None:
    """Render recurrence hotspots as subtle, hoverable bubbles."""
    if not FOLIUM_AVAILABLE or not hotspots:
        return None

    layer = folium.FeatureGroup(name=name, show=True)
    for spot in hotspots:
        area = f"{_clean_text(spot['county'])} County · {_clean_text(spot['region'])}"
        frequency = _frequency_label(spot["frequency"])
        latest = spot["latest_year"] if spot["latest_year"] is not None else "Unknown"
        tooltip = (
            f"<div style='font-family:Arial,sans-serif;min-width:220px'>"
            f"<div style='font-size:11px;letter-spacing:.08em;color:#526575;'>"
            f"APPROX. {spot['cell_km']} KM ANALYSIS AREA</div>"
            f"<div style='font-size:14px;font-weight:700;color:#172B3A;margin:3px 0 6px'>"
            f"{area}</div>"
            f"<div><b>{spot['label']} historical recurrence · {spot['score']}/100</b></div>"
            f"<div>{spot['count']:,} incidents · {frequency}</div>"
            f"<div>Active in {spot['active_years']} of {spot['observation_years']} years"
            f" · latest {latest}</div>"
            f"<div>{spot['acres']:,.0f} cumulative acres</div></div>"
        )
        popup = folium.Popup(
            tooltip
            + "<div style='margin-top:8px;padding-top:7px;border-top:1px solid #D8E0E6;"
            "font-size:10px;color:#64748B'>Historical screening indicator only; "
            "not a live ignition or re-ignition forecast.</div>",
            max_width=310,
        )
        folium.CircleMarker(
            location=[spot["lat"], spot["lon"]],
            radius=spot["radius"],
            color=spot["color"],
            weight=1.5,
            opacity=0.78,
            fill=True,
            fill_color=spot["color"],
            fill_opacity=0.16,
            tooltip=folium.Tooltip(tooltip, sticky=True),
            popup=popup,
        ).add_to(layer)
    return layer


def _add_map_legend(map_: folium.Map) -> None:
    """Add a compact recurrence-index legend inside the map."""
    rows = "".join(
        f"<div style='display:flex;align-items:center;gap:7px;margin-top:4px'>"
        f"<span style='width:10px;height:10px;border-radius:50%;background:{color};"
        f"display:inline-block'></span><span>{label}</span></div>"
        for _, label, color in reversed(RISK_BANDS)
    )
    legend = f"""
    <div style="position:fixed;left:12px;bottom:24px;z-index:9999;background:rgba(255,255,255,.94);
                border:1px solid #CBD5DC;border-radius:4px;padding:9px 11px;color:#263B4A;
                font:11px Arial,sans-serif;box-shadow:0 2px 8px rgba(15,35,50,.15)">
      <div style="font-size:10px;font-weight:700;letter-spacing:.08em">RECURRENCE INDEX</div>
      {rows}
      <div style="color:#64748B;margin-top:6px">Bubble size = incident concentration</div>
    </div>
    """
    map_.get_root().html.add_child(folium.Element(legend))


def build_fire_map(
    df,
    *,
    overlays: Sequence[object] | None = None,
    cluster: bool = True,
    max_points: int = 1500,
    show_recurrence: bool = True,
    cell_km: int = DEFAULT_CELL_KM,
    observation_years: int | None = None,
    recurrence_hotspots: Sequence[dict] | None = None,
) -> folium.Map:
    """Build the team-ready interactive WA fire map."""
    if not FOLIUM_AVAILABLE:
        raise RuntimeError("Folium is required to build the fire map.")

    data = to_wa_bounds(df)
    map_ = folium.Map(
        location=WA_CENTER,
        zoom_start=7,
        tiles="OpenStreetMap",
        control_scale=True,
        prefer_canvas=True,
    )
    folium.TileLayer(
        tiles=ESRI_SATELLITE,
        attr="Esri World Imagery",
        name="Satellite",
        overlay=False,
        show=False,
    ).add_to(map_)
    folium.TileLayer(
        tiles=ESRI_TERRAIN,
        attr="Esri World Terrain",
        name="Terrain",
        overlay=False,
        show=False,
    ).add_to(map_)
    Fullscreen(position="topleft", title="Full screen", title_cancel="Exit full screen").add_to(map_)

    # Recurrence bubbles are drawn first so individual incidents stay legible.
    hotspots = recurrence_hotspots
    if show_recurrence and hotspots is None:
        hotspots = compute_recurrence_hotspots(
            data,
            cell_km=cell_km,
            observation_years=observation_years,
        )
    if show_recurrence:
        recurrence_layer = build_recurrence_layer(hotspots or [])
        if recurrence_layer is not None:
            recurrence_layer.add_to(map_)
            _add_map_legend(map_)

    # Keep the largest individual incidents when limiting browser payload size.
    if "ACRES_BURNED" in data.columns:
        marker_data = data.nlargest(min(max_points, len(data)), "ACRES_BURNED")
    else:
        marker_data = data.head(max_points)

    fire_group = folium.FeatureGroup(name="Individual fire incidents", show=True)
    target = (
        MarkerCluster(
            options={
                "maxClusterRadius": 42,
                "showCoverageOnHover": False,
                "spiderfyOnMaxZoom": True,
            }
        ).add_to(fire_group)
        if cluster
        else fire_group
    )

    for _, row in marker_data.iterrows():
        acres_value = row.get("ACRES_BURNED", 0)
        try:
            acres = float(acres_value) if acres_value == acres_value else 0.0
        except (TypeError, ValueError):
            acres = 0.0
        incident = _clean_text(row.get("INCIDENT_NM"), "Unnamed incident")
        county = _clean_text(row.get("COUNTY_LABEL_NM"))
        cause = _clean_text(row.get("FIREGCAUSE_LABEL_NM"))
        year_value = row.get("DSCVR_YEAR", "Unknown")
        year = int(year_value) if year_value == year_value else "Unknown"

        hover = f"{incident} · {acres:,.1f} acres · {county} County"
        popup = folium.Popup(
            f"<div style='font-family:Arial,sans-serif;min-width:190px'>"
            f"<div style='font-size:15px;font-weight:700;color:#172B3A'>{incident}</div>"
            f"<div style='color:#526575;margin:3px 0 8px'>{county} County</div>"
            f"<b>{acres:,.1f} acres</b><br>Cause: {cause}<br>Discovery year: {year}"
            f"</div>",
            max_width=260,
        )
        color = _fire_color(acres)
        folium.CircleMarker(
            location=[row["LAT_COORD"], row["LON_COORD"]],
            radius=_fire_radius(acres),
            color=color,
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.72,
            tooltip=folium.Tooltip(hover, sticky=False),
            popup=popup,
        ).add_to(target)

    fire_group.add_to(map_)

    # Teammate layers (weather, wind, fuel, etc.) remain isolated and optional.
    for layer in overlays or []:
        try:
            layer.add_to(map_)
        except Exception:
            pass

    folium.LayerControl(collapsed=True, position="topright").add_to(map_)
    map_.fit_bounds([[WA_LAT_MIN, WA_LON_MIN], [WA_LAT_MAX, WA_LON_MAX]])
    return map_


def _summary_html(
    data,
    hotspots: Sequence[dict],
    cell_km: int,
    drought_context: dict | None,
) -> str:
    """Return a compact analytical summary with Logan's drought context."""
    top = hotspots[0] if hotspots else None
    top_area = (
        f"{_clean_text(top['county'])} County" if top else "No repeated cluster"
    )
    top_detail = (
        f"{top['score']}/100 · {_frequency_label(top['frequency'])}" if top else "—"
    )
    active_cells = len(hotspots)
    mapped = len(data)

    if drought_context:
        drought_value = f"DSCI {drought_context['dsci']:,.0f}"
        drought_detail = (
            f"{_clean_text(drought_context['band'])} · "
            f"{_clean_text(drought_context['date_label'])}"
        )
    else:
        drought_value = "Not loaded"
        drought_detail = "Run drought_data_pull.py"

    cards = (
        ("MAPPED INCIDENTS", f"{mapped:,}", "Current filter window", "#31566D"),
        (
            "RECURRING CELLS",
            f"{active_cells:,}",
            f"Top ~{cell_km} km analysis areas",
            "#31566D",
        ),
        ("PEAK RECURRENCE AREA", top_area, top_detail, "#8F2430"),
        ("STATEWIDE DROUGHT · LOGAN", drought_value, drought_detail, "#C75B35"),
    )
    card_html = "".join(
        f"<div style='background:#FFFFFF;border:1px solid #D6E0E6;border-top:3px solid {accent};"
        f"border-radius:3px;padding:10px 12px;min-height:70px'>"
        f"<div style='font-size:9px;font-weight:700;letter-spacing:.11em;color:#607584'>{label}</div>"
        f"<div style='font-size:17px;font-weight:700;color:#172B3A;margin-top:4px;"
        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{value}</div>"
        f"<div style='font-size:10px;color:#71818D;margin-top:2px'>{detail}</div></div>"
        for label, value, detail, accent in cards
    )
    return (
        "<div style='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));"
        f"gap:8px'>{card_html}</div>"
    )


def create_panel() -> pn.viewable.Viewable:
    """Return Paul's recurrence map as one self-contained Panel component."""
    if not FOLIUM_AVAILABLE:
        return pn.Column(
            pn.pane.Alert(
                "This map requires `folium`. Install it with `uv pip install "
                "folium --python buildathon/bin/python` (macOS/Linux) or use "
                "`buildathon/Scripts/python.exe` on Windows.",
                alert_type="warning",
            ),
            name=TITLE,
        )

    if not data_available():
        return pn.Column(
            pn.pane.Alert(
                "Fire data is unavailable. Run `python fire_data_pull.py` first.",
                alert_type="warning",
            ),
            name=TITLE,
        )

    data = to_wa_bounds(load_fire_data())
    drought_context = _latest_drought_context()
    years = sorted(int(year) for year in data["DSCVR_YEAR"].dropna().unique())
    if not years:
        return pn.Column(
            pn.pane.Alert("No dated Washington fire records are available.", alert_type="warning"),
            name=TITLE,
        )

    header = pn.pane.HTML(
        """
        <div style="background:#172B3A;border-left:5px solid #C75B35;border-radius:3px;
                    padding:14px 16px;color:#FFFFFF;font-family:Arial,sans-serif">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
            <div>
              <div style="font-size:9px;font-weight:700;letter-spacing:.15em;color:#AFC0CB">
                WASHINGTON FIRE INTELLIGENCE · SPATIAL ANALYSIS
              </div>
              <div style="font-size:20px;font-weight:700;margin-top:4px">
                Historical Recurrence Monitor
              </div>
              <div style="font-size:11px;color:#D2DDE3;margin-top:4px">
                Historical fire recurrence with Logan's statewide drought context
              </div>
            </div>
            <div style="border:1px solid #6E8796;border-radius:3px;padding:5px 7px;
                        font-size:9px;font-weight:700;letter-spacing:.08em;white-space:nowrap">
              ANALYTICAL · NOT FORECAST
            </div>
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
    min_acres = pn.widgets.FloatSlider(
        name="Minimum acres", start=0, end=1000, step=10, value=0
    )
    cell_size = pn.widgets.Select(
        name="Approximate analysis area",
        options={"~15 km": 15, "~20 km": 20, "~30 km": 30},
        value=DEFAULT_CELL_KM,
    )
    recurrence_toggle = pn.widgets.Toggle(
        name="Show recurrence layer", value=True, button_type="primary"
    )

    controls = pn.Column(
        pn.pane.HTML(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
            "color:#405A6B'>ANALYSIS CONTROLS</div>"
        ),
        pn.GridBox(
            year_range,
            cause_select,
            min_acres,
            cell_size,
            ncols=2,
            sizing_mode="stretch_width",
        ),
        recurrence_toggle,
        styles={
            "background": "#F4F7F9",
            "border": "1px solid #D6E0E6",
            "border-radius": "3px",
            "padding": "11px",
        },
        sizing_mode="stretch_width",
    )

    @pn.depends(
        year_range,
        cause_select,
        min_acres,
        cell_size,
        recurrence_toggle,
    )
    def analysis_view(yr_range, causes, acres_min, cell_km, show_recurrence):
        low, high = yr_range
        filtered = data[
            (data["DSCVR_YEAR"] >= low) & (data["DSCVR_YEAR"] <= high)
        ]
        if causes:
            filtered = filtered[filtered["FIREGCAUSE_LABEL_NM"].isin(causes)]
        if acres_min:
            filtered = filtered[filtered["ACRES_BURNED"] >= acres_min]

        if filtered.empty:
            return pn.pane.Alert(
                "No Washington fire records match the current analysis settings.",
                alert_type="info",
            )

        observation_years = high - low + 1
        hotspots = compute_recurrence_hotspots(
            filtered,
            cell_km=cell_km,
            observation_years=observation_years,
        )
        map_ = build_fire_map(
            filtered,
            overlays=None,
            show_recurrence=show_recurrence,
            cell_km=cell_km,
            observation_years=observation_years,
            recurrence_hotspots=hotspots,
        )
        summary = pn.pane.HTML(
            _summary_html(filtered, hotspots, cell_km, drought_context),
            sizing_mode="stretch_width",
        )
        map_pane = pn.pane.plot.Folium(
            map_, height=500, sizing_mode="stretch_width"
        )
        return pn.Column(summary, map_pane, sizing_mode="stretch_width")

    methodology = pn.pane.HTML(
        """
        <div style="background:#F7F9FA;border:1px solid #D6E0E6;border-left:3px solid #C75B35;
                    border-radius:3px;padding:10px 12px;color:#526575;font:10px Arial,sans-serif;
                    line-height:1.45">
          <b style="color:#263B4A">INTERPRETATION.</b>
          Larger translucent bubbles indicate more recorded incidents inside an approximate analysis cell.
          The relative recurrence index is a log-scaled measure of incident concentration, so denser
          clusters are always larger and receive an equal-or-higher index. Hover a bubble for local
          frequency, active years, and latest recorded incident; hover or click an incident dot
          for fire details. Logan's DSCI card supplies current statewide drought context only and does
          not spatially modify the local recurrence index. This historical indicator does not predict
          active ignition or re-ignition risk; operational risk also requires local weather, fuels,
          wind, and incident-status data.
        </div>
        """,
        sizing_mode="stretch_width",
    )

    return pn.Column(
        header,
        controls,
        analysis_view,
        methodology,
        name=TITLE,
        sizing_mode="stretch_width",
        styles={"gap": "10px"},
    )

"""
Paul's widget -- an interactive, Google-Maps-style live map of WA wildfires.

Built on Folium (Leaflet), so it has real pan/zoom and switchable basemaps
(street + satellite), unlike a static scatter. Fires are drawn as circle
markers sized and colored by acres burned, with popups for details.

INTEGRATION FOR TEAMMATES
-------------------------
This module exposes a reusable map builder so other widgets (e.g. Logan's
weather system) can render their own data on the *same* Washington map:

    from widgets.paul import build_fire_map

    m = build_fire_map(my_fire_df, overlays=[my_weather_layer])

- `build_fire_map(df, overlays=None, ...)` returns a `folium.Map`.
- `overlays` is a list of objects with an `.add_to(map)` method -- any Folium
  layer/FeatureGroup works. Logan can build a weather `FeatureGroup` (stations,
  heat layer, wind markers, etc.) and pass it in; it'll appear as a toggleable
  layer in the map's LayerControl, overlaid on the fires.
- `make_weather_layer(points, ...)` is a convenience helper that turns a list
  of weather readings into a ready-to-overlay Folium FeatureGroup, so the
  weather widget doesn't have to know Folium details.

Per the team contract (AGENTS.md): load data via `load_fire_data()`, filter to
WA bounds for maps, and expose a single `create_panel()`.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import panel as pn

from data_access import data_available, load_fire_data

# Folium (Leaflet) powers the interactive map. It's imported lazily so that if
# a teammate hasn't installed it yet, ONLY this widget shows a friendly notice
# instead of breaking the whole app's import. Install with:
#   uv pip install folium --python buildathon/bin/python
try:
    import folium
    from folium.plugins import MarkerCluster

    FOLIUM_AVAILABLE = True
except ImportError:  # pragma: no cover
    folium = None
    MarkerCluster = None
    FOLIUM_AVAILABLE = False

TITLE = "Paul's Map -- Live WA Wildfire Map"

# Washington geographic bounds (lat/lon) for cleaning coordinates and framing.
WA_LAT_MIN, WA_LAT_MAX = 45.5, 49.05
WA_LON_MIN, WA_LON_MAX = -124.85, -116.90
WA_CENTER = [47.4, -120.5]

# Free, no-API-key basemaps. (CartoDB now needs a key, so we avoid it.)
ESRI_SATELLITE = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_TERRAIN = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Terrain_Base/MapServer/tile/{z}/{y}/{x}"
)


def _fire_color(acres: float) -> str:
    """Red-scale color by fire size."""
    if acres >= 1000:
        return "#7f0000"
    if acres >= 100:
        return "#b91c1c"
    if acres >= 10:
        return "#ef4444"
    if acres >= 1:
        return "#f59e0b"
    return "#84cc16"


def _fire_radius(acres: float) -> float:
    """Marker radius (px) scaled by fire size, clamped to a sane range."""
    if acres >= 1000:
        return 12
    if acres >= 100:
        return 9
    if acres >= 10:
        return 7
    if acres >= 1:
        return 5
    return 4


def to_wa_bounds(df):
    """Return rows with valid lat/lon inside Washington."""
    df = df.dropna(subset=["LAT_COORD", "LON_COORD"])
    return df[
        df["LAT_COORD"].between(WA_LAT_MIN, WA_LAT_MAX)
        & df["LON_COORD"].between(WA_LON_MIN, WA_LON_MAX)
    ]


def make_weather_layer(
    points: Iterable[dict],
    *,
    name: str = "Weather",
    color: str = "#2563eb",
) -> folium.FeatureGroup:
    """
    Convenience helper for the weather widget (Logan) to build an overlay.

    `points` is an iterable of dicts, each with at least `lat` and `lon`, and
    optionally `label` (popup text) and `value` (e.g. temperature). Returns a
    Folium FeatureGroup ready to pass into `build_fire_map(overlays=[...])`.

    This keeps the weather code decoupled from Folium specifics -- Logan can
    hand over plain data and still get a layer that lines up with the fire map.
    """
    group = folium.FeatureGroup(name=name, show=True)
    for p in points:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        label = p.get("label", "")
        value = p.get("value")
        popup = label if value is None else f"{label}: {value}"
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color=color,
            weight=2,
            fill=True,
            fill_opacity=0.5,
            popup=popup or None,
        ).add_to(group)
    return group


def build_zone_layer(df, *, name: str = "Fire zones (hover)") -> object | None:
    """
    Build a Folium layer that outlines each DNR region (zone) very faintly, so
    the map stays clean -- the zone only "lights up" (fills in) when you hover
    over it, showing the region name and its fire stats in a tooltip.

    Zone shapes are derived from the fire points themselves (a convex hull per
    region), so they reflect exactly the data currently shown and react to the
    active filters -- no external boundary file needed.

    Returns None if folium/shapely aren't available or there's nothing to draw.
    """
    if not FOLIUM_AVAILABLE:
        return None
    try:
        from shapely.geometry import MultiPoint
    except ImportError:
        return None

    data = to_wa_bounds(df)
    if data.empty or "REGION_NAME" not in data.columns:
        return None

    total_fires = len(data)

    # Collect each zone as a GeoJSON feature so we can attach hover behavior.
    features = []
    for region, grp in data.groupby("REGION_NAME"):
        if region is None or len(grp) < 3:
            continue  # need at least 3 points to form an area
        pts = list(zip(grp["LON_COORD"], grp["LAT_COORD"]))
        hull = MultiPoint(pts).convex_hull
        if hull.geom_type != "Polygon":
            continue  # collinear points -> no area

        fires = len(grp)
        acres = float(grp["ACRES_BURNED"].sum()) if "ACRES_BURNED" in grp else 0.0
        share = fires / total_fires if total_fires else 0.0
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    # GeoJSON uses [lon, lat] order.
                    "coordinates": [[list(c) for c in hull.exterior.coords]],
                },
                "properties": {
                    "Zone": region,
                    "Fires": f"{fires:,} ({share*100:.0f}% of shown)",
                    "Acres burned": f"{acres:,.0f}",
                },
            }
        )

    if not features:
        return None

    group = folium.FeatureGroup(name=name, show=True)
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        # Default: barely-there outline, no fill -> keeps the map uncluttered.
        style_function=lambda _f: {
            "color": "#9ca3af",
            "weight": 1,
            "opacity": 0.35,
            "fillOpacity": 0.0,
        },
        # On hover: the zone fills in softly and its border strengthens.
        highlight_function=lambda _f: {
            "color": "#b91c1c",
            "weight": 2,
            "opacity": 0.9,
            "fillColor": "#ef4444",
            "fillOpacity": 0.25,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["Zone", "Fires", "Acres burned"],
            aliases=["Zone", "Fires", "Acres burned"],
            sticky=True,
        ),
    ).add_to(group)

    return group


def build_fire_map(
    df,
    *,
    overlays: Sequence[object] | None = None,
    cluster: bool = True,
    max_points: int = 1500,
    highlight_zones: bool = False,
) -> folium.Map:
    """
    Build an interactive Folium map of WA wildfires.

    Parameters
    ----------
    df : DataFrame
        Fire records (will be filtered to WA bounds).
    overlays : sequence of Folium layers, optional
        Extra layers to add on top -- e.g. a weather FeatureGroup from
        `make_weather_layer()`. Each must support `.add_to(map)`. They appear
        as toggleable layers in the LayerControl so teammates' data can be
        turned on/off independently of the fires.
    cluster : bool
        Cluster dense fire markers for performance/readability.
    max_points : int
        Cap the number of fire markers rendered (largest fires first).
    highlight_zones : bool
        Shade each DNR region (zone) with intensity scaled by fire activity.

    Returns
    -------
    folium.Map
    """
    data = to_wa_bounds(df)

    m = folium.Map(location=WA_CENTER, zoom_start=7, tiles="OpenStreetMap")
    # Alternate key-free basemaps for a Google-Maps-style satellite/terrain toggle.
    folium.TileLayer(tiles=ESRI_SATELLITE, attr="Esri", name="Satellite").add_to(m)
    folium.TileLayer(tiles=ESRI_TERRAIN, attr="Esri", name="Terrain").add_to(m)

    # Highlighted fire zones go under the markers. Built from the full filtered
    # set (not the marker-capped subset) so the shaded areas stay accurate.
    if highlight_zones:
        zone_layer = build_zone_layer(data)
        if zone_layer is not None:
            zone_layer.add_to(m)

    # Cap markers for performance, largest fires first.
    if "ACRES_BURNED" in data.columns:
        marker_data = data.nlargest(min(max_points, len(data)), "ACRES_BURNED")
    else:
        marker_data = data.head(max_points)

    fire_group = folium.FeatureGroup(name="Wildfires", show=True)
    target = MarkerCluster().add_to(fire_group) if cluster else fire_group

    for _, r in marker_data.iterrows():
        acres = float(r.get("ACRES_BURNED", 0) or 0)
        name = r.get("INCIDENT_NM", "Unnamed")
        county = r.get("COUNTY_LABEL_NM", "Unknown")
        cause = r.get("FIREGCAUSE_LABEL_NM", "Unknown")
        year = r.get("DSCVR_YEAR", "")
        popup = folium.Popup(
            f"<b>{name}</b><br>{county} County<br>"
            f"{acres:,.1f} acres<br>Cause: {cause}<br>Year: {year}",
            max_width=240,
        )
        folium.CircleMarker(
            location=[r["LAT_COORD"], r["LON_COORD"]],
            radius=_fire_radius(acres),
            color=_fire_color(acres),
            weight=1,
            fill=True,
            fill_color=_fire_color(acres),
            fill_opacity=0.7,
            popup=popup,
        ).add_to(target)

    fire_group.add_to(m)

    # Let teammates drop their own layers (weather, etc.) onto the same map.
    for layer in overlays or []:
        try:
            layer.add_to(m)
        except Exception:
            # A broken overlay should never take down the map.
            pass

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def create_panel() -> pn.viewable.Viewable:
    """Return Paul's interactive map widget as a Panel component."""
    if not FOLIUM_AVAILABLE:
        return pn.Column(
            f"## {TITLE}",
            pn.pane.Alert(
                "This map needs `folium`. Install it with:\n\n"
                "```\nuv pip install folium --python buildathon/bin/python\n```",
                alert_type="warning",
            ),
            name=TITLE,
        )

    if not data_available():
        return pn.Column(
            f"## {TITLE}",
            pn.pane.Alert(
                "Data not found. Run `python fire_data_pull.py` first.",
                alert_type="warning",
            ),
            name=TITLE,
        )

    df = load_fire_data()
    wa = to_wa_bounds(df)

    # --- Filters ---------------------------------------------------------
    years = sorted(int(y) for y in wa["DSCVR_YEAR"].dropna().unique())
    year_range = pn.widgets.IntRangeSlider(
        name="Discovery year",
        start=years[0],
        end=years[-1],
        value=(years[0], years[-1]),
        step=1,
    )
    cause_select = pn.widgets.MultiChoice(
        name="Cause",
        options=sorted(wa["FIREGCAUSE_LABEL_NM"].dropna().unique().tolist()),
        placeholder="All causes",
    )
    min_acres = pn.widgets.FloatSlider(
        name="Min acres burned", start=0, end=1000, step=10, value=0
    )

    @pn.depends(year_range, cause_select, min_acres)
    def _map(yr_range, causes, acres_min):
        lo, hi = yr_range
        data = wa[(wa["DSCVR_YEAR"] >= lo) & (wa["DSCVR_YEAR"] <= hi)]
        if causes:
            data = data[data["FIREGCAUSE_LABEL_NM"].isin(causes)]
        if acres_min:
            data = data[data["ACRES_BURNED"] >= acres_min]
        if data.empty:
            return pn.pane.Alert(
                "No fires match the current filters.", alert_type="info"
            )
        # overlays=None for now; Logan's weather layer can be passed here once
        # his widget exposes its data (see make_weather_layer / build_fire_map).
        fmap = build_fire_map(data, overlays=None)
        return pn.pane.plot.Folium(fmap, height=460, sizing_mode="stretch_width")

    controls = pn.Row(year_range, cause_select, min_acres)
    note = pn.pane.Markdown(
        "Interactive map (pan/zoom, switch street/satellite/terrain in the "
        "layer control). Markers sized & colored by acres burned. "
        "Built to accept teammate overlays -- e.g. Logan's weather layer via "
        "`build_fire_map(df, overlays=[...])`.",
        styles={"color": "#6b7280", "font-size": "12px"},
    )

    return pn.Column(controls, _map, note, name=TITLE, sizing_mode="stretch_width")

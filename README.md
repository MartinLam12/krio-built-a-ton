# Washington Wildfire Watch

An MVP "where to intervene" dashboard for Washington State wildfire data. It
ranks counties by wildfire burden and lets you explore fire locations, causes,
and year-over-year trends.

Built on the public **DNR Fire Statistics 2008–Present** point layer published
on the [Washington State Geospatial Open Data Portal](https://geo.wa.gov/datasets/dabefcb8f03549b49bee7564d4c3c4b5_2/explore)
(served from the WA DNR ArcGIS REST service). ~31,900 fire records.

## Stack

- **Panel** — layout, widgets, templating
- **Bokeh** — interactive tile map of fire locations
- **Plotly** — ranking, trend, and cause charts
- **pandas / requests** — data access and shaping

## What it does

- **County priority ranking** — a transparent 0–100 score blending total acres
  burned (45%), fire count (30%), and recent 5-year acres (25%). This is the
  core "where should mitigation effort go" view.
- **Interactive map** — every fire plotted, sized by acres and colored by
  severity, with hover details.
- **Trend chart** — acres burned (bars) and fire count (line) by year.
- **Cause breakdown** — fires by general cause, colored by acreage.
- **Filters** — fire year range, county, and cause, applied across all views.

## Run it

```bash
pip install -r requirements.txt
panel serve app.py --show
```

The first launch downloads the full layer from the DNR service and caches it
locally as `wildfire_cache.parquet` (refreshed daily). To force a refresh:

```bash
python -c "import data_source; data_source.load(force_refresh=True)"
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | Panel dashboard (widgets, charts, map, layout) |
| `data_source.py` | Pulls + cleans + caches the DNR REST layer |
| `requirements.txt` | Python dependencies |

## Data notes & caveats

- This layer shows **where and how severely** fires burned. It does not include
  forest-density or treatment information, so it cannot by itself explain *why*
  an area burned — it identifies priority areas, not root causes.
- "Undetermined" is the single largest cause category by count; cause data is
  incomplete for some records.
- Coordinates are filtered to a Washington bounding box for the map; a small
  number of records with missing/implausible coordinates are omitted from the
  map but still counted in statistics.
- Source data © WA DNR. Locations are approximate.

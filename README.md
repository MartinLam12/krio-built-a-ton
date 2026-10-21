# krio-built-a-ton — WA DNR Fire Statistics

Tools for pulling and visualizing the Washington DNR Fire Statistics
(2008-Present) dataset.

## Scripts

- `fire_data_pull.py` — pulls all records from the WA DNR ArcGIS REST service
  (paginated, 2000 rows/request) and saves them to
  `data/dnr_fire_statistics.parquet`.
- `dashboard.py` — an interactive [Panel](https://panel.holoviz.org/) dashboard
  with summary metrics, filters, a fires-per-year chart, a location map, and a
  filterable data table.

> Note: the `data/` folder is generated and is **not** committed. Run the data
> pull first to create it.

## Setup

Requires Python 3.12+. We use [uv](https://docs.astral.sh/uv/) to create the
environment.

```bash
# create the virtual environment
uv venv buildathon

# install dependencies
uv pip install panel jupyter notebook pandas numpy pyarrow hvplot --python buildathon/Scripts/python.exe
```

On macOS/Linux the interpreter path is `buildathon/bin/python` instead of
`buildathon/Scripts/python.exe`.

## Usage

```bash
# 1. pull the data (creates data/dnr_fire_statistics.parquet)
buildathon/Scripts/python.exe fire_data_pull.py

# 2. launch the dashboard (opens in your browser)
buildathon/Scripts/panel.exe serve dashboard.py --show
```

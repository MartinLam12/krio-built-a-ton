# AGENTS.md

Guidance for AI coding agents (e.g. Kiro) working in this repo. The goal is a
team-built Panel dashboard where four people each contribute one widget without
stepping on each other.

## Project overview

An interactive [Panel](https://panel.holoviz.org/) dashboard for the WA DNR
Fire Statistics (2008-Present) dataset. The base app lays out four
independently-owned widgets in a grid.

```
app.py              # base app — lays out everyone's widgets
data_access.py      # shared, cached data loader
fire_data_pull.py   # pulls data from the WA DNR ArcGIS REST API into data/
widgets/
  martin.py  jaize.py  paul.py  logan.py   # one widget per teammate
data/               # generated parquet (git-ignored, not committed)
```

## Environment

- Python **3.12+**, managed with [uv](https://docs.astral.sh/uv/).
- The virtual environment is `buildathon/` at the repo root (git-ignored).
- Interpreter: `buildathon/Scripts/python.exe` (Windows) or
  `buildathon/bin/python` (macOS/Linux).
- Dependencies: `panel`, `jupyter`, `notebook`, `pandas`, `numpy`, `pyarrow`,
  `hvplot`. Install new deps with
  `uv pip install <pkg> --python buildathon/Scripts/python.exe`.

## Common commands

```bash
# pull the data (creates data/dnr_fire_statistics.parquet)
buildathon/Scripts/python.exe fire_data_pull.py

# serve the dashboard
buildathon/Scripts/panel.exe serve app.py --show --autoreload

# quick import smoke-test before serving
buildathon/Scripts/python.exe -c "import app; print('ok')"
```

## Rules for agents

### Scope: edit one widget file only

- When asked to build or change a teammate's widget, edit **only** that file in
  `widgets/` (e.g. `widgets/martin.py`).
- **Do not edit `app.py`** unless explicitly asked to change the base app or the
  list of contributors. It discovers widgets automatically.
- Don't edit another teammate's widget file.

### Widget contract

- Each widget module exposes a single `create_panel()` that returns **one**
  Panel component (a pane, widget, `Column`, `Row`, etc.).
- Set a `name=` on the returned component so it gets a clean title.
- Keep the module-level `TITLE` constant; the base app uses it for the card.
- Load data via `from data_access import load_fire_data` — **never** read the
  parquet file directly, and don't hard-code its path.
- Handle the missing-data case: if `data_available()` is `False`, return a
  friendly message instead of crashing (see the existing placeholder).

### Data notes

- `load_fire_data()` returns a cached DataFrame and adds derived columns:
  `DSCVR_DATE` (datetime) and `DSCVR_YEAR` (int) from the epoch-ms `DSCVR_DT`,
  and cleans `ACRES_BURNED`.
- Useful raw columns: `INCIDENT_NM`, `COUNTY_LABEL_NM`, `REGION_NAME`,
  `FIREGCAUSE_LABEL_NM`, `ACRES_BURNED`, `LAT_COORD`, `LON_COORD`,
  `FIREEVNT_CLASS_LABEL_NM`, `DSCVR_MONTH`.
- Lat/lon include some bad values (0,0 etc.). For maps, filter to WA bounds:
  lat 45–49.5, lon -125 to -116.

### Charts

- Use `hvplot` (already a dependency) for charts; `import hvplot.pandas` to
  register the `.hvplot` accessor.
- For bar charts over years, cast the year to a **string** before plotting to
  avoid a numeric-axis crash in the installed holoviews/bokeh versions.

### Verification

- Before claiming a change works, run the import smoke-test above and, if you
  changed a widget, confirm the app still serves without errors.
- Keep widgets self-contained so one failing widget can't break the others.

## Git

- `data/`, `buildathon/`, `__pycache__/`, and `brainstorm.txt` are git-ignored.
  Never commit generated data or the virtual environment.
- Stage files by name; avoid `git add .`.
- Don't push to `main` unless asked — coordinate branches with the team.

# krio-built-a-ton — WA DNR Fire Dashboard

A team-built [Panel](https://panel.holoviz.org/) dashboard for the Washington
DNR Fire Statistics (2008-Present) dataset. Four contributors each own one
widget; the base app wires them together automatically.

## Project layout

```
app.py              # base dashboard — lays out everyone's widgets (don't edit)
data_access.py      # shared data loader — use load_fire_data() in your widget
fire_data_pull.py   # pulls the data from the WA DNR API into data/
widgets/
  martin.py         # Martin's widget
  jaize.py          # Jaize's widget
  paul.py           # Paul's widget
  logan.py          # Logan's widget
data/               # generated parquet (not committed)
```

## Run it locally

You need **Python 3.12+** and [uv](https://docs.astral.sh/uv/). Run these from
the repo root.

### 1. Create the virtual environment

```bash
uv venv buildathon
```

### 2. Install dependencies

```bash
uv pip install panel jupyter notebook pandas numpy pyarrow hvplot --python buildathon/Scripts/python.exe
```

> On macOS/Linux, use `buildathon/bin/python` wherever you see
> `buildathon/Scripts/python.exe` below.

### 3. Pull the data

This creates `data/dnr_fire_statistics.parquet` (about 32k fire records). Run
it once:

```bash
buildathon/Scripts/python.exe fire_data_pull.py
```

### 4. Launch the dashboard

```bash
buildathon/Scripts/panel.exe serve app.py --show
```

Your browser opens to **http://localhost:5006/app**. Leave it running — Panel
auto-reloads when you save a file if you add `--autoreload`:

```bash
buildathon/Scripts/panel.exe serve app.py --show --autoreload
```

## Building your widget

Each person edits **only their own file** in `widgets/`, so nobody creates
merge conflicts in the base app.

1. Open your file (e.g. `widgets/martin.py`).
2. Fill in `create_panel()` so it returns a single Panel component.
3. Load data with `load_fire_data()` from `data_access` — don't read the
   parquet directly.
4. Save and refresh the browser (or use `--autoreload`).

A quick way to build it: point Kiro at your file, for example —

> "In `widgets/martin.py`, make `create_panel()` show a bar chart of the top 10
> counties by total acres burned using the fire data."

If a widget errors out, only its card shows the error — the rest of the
dashboard keeps working.

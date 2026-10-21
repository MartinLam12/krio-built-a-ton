"""
Jaize's widget.

HOW TO BUILD YOUR WIDGET
------------------------
1. Load shared data with `load_fire_data()` (don't read the parquet directly).
2. Build your Panel component(s) inside `create_panel()`.
3. Return a single Panel object (a pane, widget, Column, Row, etc.).
4. Give it a `name=` so it shows up with a nice title in the dashboard.

That's it -- the base app (app.py) picks this up automatically. You don't
need to touch app.py or anyone else's file.

Example prompt for Kiro:
    "In widgets/jaize.py, make create_panel() show a line chart of fires per
     year using the fire data."
"""

import panel as pn

from data_access import data_available, load_fire_data

TITLE = "Jaize's Widget"


def create_panel() -> pn.viewable.Viewable:
    """Return Jaize's widget as a Panel component."""
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

    # TODO (Jaize): replace this placeholder with your real widget.
    return pn.Column(
        f"## {TITLE}",
        pn.pane.Markdown(
            f"Placeholder. The data has **{len(df):,}** rows and "
            f"**{df.shape[1]}** columns.\n\n"
            "Edit `create_panel()` in `widgets/jaize.py` to build your view."
        ),
        name=TITLE,
    )

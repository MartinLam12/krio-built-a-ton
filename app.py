"""
Base dashboard app -- WA DNR Fire Statistics.

This is the shared skeleton. Each teammate builds their widget in their own
file under `widgets/` (martin.py, jaize.py, paul.py, logan.py) and the base app
lays them out automatically. You normally should NOT need to edit this file.

Run locally with:
    ..\\buildathon\\Scripts\\panel.exe serve app.py --show
"""

import panel as pn

from data_access import data_available
from widgets import jaize, logan, martin, paul

pn.extension("tabulator", sizing_mode="stretch_width")

# The four widget modules, in display order. To add/remove a contributor,
# edit this list -- nothing else in the app needs to change.
WIDGET_MODULES = [martin, jaize, paul, logan]


def safe_create(module) -> pn.viewable.Viewable:
    """
    Call a widget module's create_panel(), isolating failures.

    If one widget raises, we show the error in that card instead of crashing
    the whole dashboard -- so a work-in-progress widget never blocks the team.
    """
    name = getattr(module, "TITLE", module.__name__)
    try:
        return module.create_panel()
    except Exception as exc:  # noqa: BLE001 - we want to catch everything here
        return pn.Column(
            f"## {name}",
            pn.pane.Alert(
                f"This widget raised an error:\n\n```\n{exc}\n```",
                alert_type="danger",
            ),
            name=name,
        )


def build_cards() -> list[pn.Card]:
    """Wrap each widget in a collapsible card for a tidy grid layout."""
    cards = []
    for module in WIDGET_MODULES:
        panel = safe_create(module)
        title = getattr(module, "TITLE", module.__name__)
        cards.append(
            pn.Card(
                panel,
                title=title,
                collapsible=True,
                margin=10,
                sizing_mode="stretch_width",
            )
        )
    return cards


def build_grid(cards: list[pn.Card]) -> pn.GridBox:
    """Arrange the widget cards in a responsive 2-column grid."""
    return pn.GridBox(*cards, ncols=2, sizing_mode="stretch_width")


# ---------------------------------------------------------------------------
# Assemble the template
# ---------------------------------------------------------------------------
data_banner = (
    pn.pane.Alert(
        "No data file found. Run `python fire_data_pull.py` to generate "
        "`data/dnr_fire_statistics.parquet`. Widgets will show placeholders "
        "until then.",
        alert_type="warning",
    )
    if not data_available()
    else pn.pane.Markdown(
        "Fire-statistics data loaded. Each card below is owned by one "
        "teammate -- edit your file in `widgets/` to build your view.",
        styles={"color": "#6b7280"},
    )
)

template = pn.template.FastListTemplate(
    title="WA DNR Fire Dashboard -- Team Build",
    header_background="#b91c1c",
    accent_base_color="#b91c1c",
    main=[data_banner, build_grid(build_cards())],
)

template.servable()

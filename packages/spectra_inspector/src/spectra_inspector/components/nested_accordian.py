from typing import Any

import dash_bootstrap_components as dbc
from dash import html


def _render_value(val: Any) -> str:
    """Convert values into display-friendly strings."""
    if isinstance(val, (tuple, list)):
        return ", ".join(str(v) for v in val)
    if isinstance(val, bool):
        return "True" if val else "False"
    return str(val)


def _dict_to_table(d: dict[str, Any]) -> dbc.Table:
    """Render a flat dict as a Bootstrap table."""
    rows = []
    for k, v in d.items():
        # skip nested dicts here; they are handled separately in accordion
        if isinstance(v, dict):
            continue

        rows.append(
            html.Tr(
                [
                    html.Td(k, style={"fontWeight": "bold", "width": "40%"}),
                    html.Td(_render_value(v)),
                ]
            )
        )

    return dbc.Table(
        [html.Tbody(rows)],
        bordered=True,
        striped=True,
        hover=True,
        size="sm",
    )


def put_dict_in_accordian(d: dict[str, Any]) -> dbc.Accordion:
    items = []

    # First: render non-dict fields as a table (if any exist)
    non_dicts = {k: v for k, v in d.items() if not isinstance(v, dict)}
    if non_dicts:
        items.append(_dict_to_table(non_dicts))

    # Second: recurse only into dicts → accordions
    for k, v in d.items():
        if isinstance(v, dict):
            items.append(
                dbc.AccordionItem(
                    put_dict_in_accordian(v),
                    title=k,
                )
            )

    return dbc.Accordion(items, start_collapsed=True, flush=True)


def nested_accordian(val: dict[str, Any]) -> dbc.Accordion:
    return put_dict_in_accordian(val)

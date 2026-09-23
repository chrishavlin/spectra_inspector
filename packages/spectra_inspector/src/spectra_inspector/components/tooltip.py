"""Hover-only tooltips that close when the mouse has left.

``dbc.Tooltip`` defaults to ``trigger="hover focus"``, and the focus half
shows a tooltip whenever its target takes focus with the mouse elsewhere: a
dropdown handing focus back to its button after a pick, or the window
regaining focus while a toolbox button is focused. Nothing hides it until the
target blurs, and a click on a plotly graph does not move focus, so the
tooltip outlives the mouse leaving and clicks elsewhere.

The hover half has a race of its own. The component mirrors its open flag
into a ref from a passive effect, and its mouseout handler consults that ref:
a mouseout landing between the show timer firing and that effect running is
ignored, and the tooltip stays open with the mouse gone until the target is
hovered and left again. A quick pass over a toolbar button does it several
times in twenty. ``is_open`` only seeds the component's state, so nothing
outside it can close the tooltip except another mouseout on the target.
``assets/hover_tooltip.js`` replays that mouseout: whenever the pointer
enters an element, every shown tooltip whose target and body are both
elsewhere gets one. It finds the target through the tooltip's id, which
``hover_tooltip`` builds from the target's rendered DOM id.
"""

import json
from typing import Any

import dash_bootstrap_components as dbc

HOVER_TOOLTIP_TYPE = "hover-tooltip"


def dom_id(component_id: str | dict[str, Any]) -> str:
    """The ``id`` attribute Dash renders for a component id: a dict becomes
    its keys-sorted, whitespace-free JSON (``dash._utils.stringify_id``)."""
    if isinstance(component_id, str):
        return component_id
    return json.dumps(component_id, sort_keys=True, separators=(",", ":"))


def hover_tooltip_id(target: str | dict[str, Any]) -> dict[str, str]:
    return {"type": HOVER_TOOLTIP_TYPE, "index": dom_id(target)}


def hover_tooltip(
    text: str, target: str | dict[str, Any], **kwargs: Any
) -> dbc.Tooltip:
    kwargs.setdefault("id", hover_tooltip_id(target))
    return dbc.Tooltip(text, target=target, trigger="hover", **kwargs)

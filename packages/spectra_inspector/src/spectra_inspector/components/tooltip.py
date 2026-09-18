"""Hover-only tooltips.

``dbc.Tooltip`` defaults to ``trigger="hover focus"``, and the focus half
shows a tooltip whenever its target takes focus with the mouse elsewhere: a
dropdown handing focus back to its button after a pick, or the window
regaining focus while a toolbox button is focused. Nothing hides it until the
target blurs, and a click on a plotly graph does not move focus, so the
tooltip outlives the mouse leaving and clicks elsewhere.
"""

from typing import Any

import dash_bootstrap_components as dbc


def hover_tooltip(
    text: str, target: str | dict[str, Any], **kwargs: Any
) -> dbc.Tooltip:
    return dbc.Tooltip(text, target=target, trigger="hover", **kwargs)

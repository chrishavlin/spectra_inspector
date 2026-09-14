"""One toolbar for every image panel.

The panels' own plotly modebars are switched off; the tools live in a single
card above the panels and act on all of them at once through the shared view
and shapes stores, the same route a zoom dragged out on one panel takes to
reach the others.

A *tool* is a plotly ``dragmode`` (what a drag on a panel does) and is
persistent: the active one is whatever the shared view's ``dragmode`` holds.
An *action* runs once when clicked (zoom in, zoom out, erase the box).
"""

from dataclasses import dataclass
from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.view_sync import ensure_view

TOOLBOX_TITLE = "Bitmap Image Toolbox"


@dataclass(frozen=True)
class imageTool:
    id: str  # doubles as the plotly dragmode
    label: str
    icon: str
    tooltip: str


@dataclass(frozen=True)
class imageAction:
    id: str
    label: str
    icon: str
    tooltip: str


TOOLS: tuple[imageTool, ...] = (
    imageTool(
        "drawrect",
        "Draw box",
        "fa-solid fa-vector-square",
        "Drag out a box: the spectrum sums over the pixels inside it",
    ),
    imageTool(
        "zoom", "Zoom", "fa-solid fa-magnifying-glass", "Drag out a box to zoom into"
    ),
    imageTool("pan", "Pan", "fa-solid fa-hand", "Drag to move the view"),
)

ACTIONS: tuple[imageAction, ...] = (
    imageAction(
        "zoomin",
        "Zoom in",
        "fa-solid fa-magnifying-glass-plus",
        "Zoom in on the centre",
    ),
    imageAction(
        "zoomout",
        "Zoom out",
        "fa-solid fa-magnifying-glass-minus",
        "Zoom out from the centre",
    ),
    imageAction("eraseshape", "Erase box", "fa-solid fa-eraser", "Remove the box"),
)

# what get_new_im puts on a fresh figure, and so what a view without a dragmode
# means
DEFAULT_TOOL = "drawrect"

TOOL_IDS = tuple(tool.id for tool in TOOLS)
ACTION_IDS = tuple(action.id for action in ACTIONS)

# plotly's own zoom in / zoom out buttons halve and double the ranges
ZOOM_FACTORS = {"zoomin": 0.5, "zoomout": 2.0}


class imageToolboxLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = ("div", "tool", "action")

    def __init__(self, id_type_base: str = "image-toolbox") -> None:
        super().__init__(id_type_base, None)

    @property
    def tool(self) -> str:
        return self.full_id("-tool")

    @property
    def action(self) -> str:
        return self.full_id("-action")

    def tool_id(self, tool: str) -> dict[str, str]:
        """The pattern-matching id of a tool button, indexed by the tool."""
        return {"type": self.tool, "index": tool}

    def action_id(self, action: str) -> dict[str, str]:
        return {"type": self.action, "index": action}


def active_tool(view: dict[str, Any] | None) -> str:
    """The tool the shared view holds; no dragmode means the default."""
    dragmode = ensure_view(view)["dragmode"]
    return dragmode if isinstance(dragmode, str) else DEFAULT_TOOL


def tool_button_states(view: dict[str, Any] | None) -> list[bool]:
    """``active`` for each tool button, in TOOLS order."""
    current = active_tool(view)
    return [tool.id == current for tool in TOOLS]


def _icon_button(
    button_id: dict[str, str], icon: str, label: str, *, active: bool = False
) -> dbc.Button:
    return dbc.Button(
        [html.I(className=f"{icon} me-1"), label],
        id=button_id,
        n_clicks=0,
        color="secondary",
        outline=True,
        active=active,
        className="text-nowrap",
    )


def image_toolbox_layout(
    id_type_base: str = "image-toolbox",
) -> tuple[dbc.Card, imageToolboxLayoutIDs]:
    ids = imageToolboxLayoutIDs(id_type_base=id_type_base)
    states = tool_button_states(None)

    tool_group = dbc.ButtonGroup(
        [
            _icon_button(ids.tool_id(tool.id), tool.icon, tool.label, active=state)
            for tool, state in zip(TOOLS, states, strict=True)
        ],
        size="sm",
    )
    action_group = dbc.ButtonGroup(
        [
            _icon_button(ids.action_id(action.id), action.icon, action.label)
            for action in ACTIONS
        ],
        size="sm",
    )
    tooltips = [
        dbc.Tooltip(tool.tooltip, target=ids.tool_id(tool.id), placement="bottom")
        for tool in TOOLS
    ] + [
        dbc.Tooltip(action.tooltip, target=ids.action_id(action.id), placement="bottom")
        for action in ACTIONS
    ]

    card = dbc.Card(
        [
            dbc.CardHeader(TOOLBOX_TITLE, className="px-2 py-1"),
            dbc.CardBody(
                [
                    html.Div(
                        [tool_group, action_group],
                        className="d-flex flex-wrap align-items-center gap-2",
                    ),
                    *tooltips,
                ],
                className="p-2",
            ),
        ],
        id=ids.div,
        className="mb-2",
    )
    return card, ids

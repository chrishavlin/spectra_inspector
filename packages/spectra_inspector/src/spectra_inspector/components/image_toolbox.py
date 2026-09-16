"""One toolbar for every image panel.

The panels' own plotly modebars are switched off; the tools live in a single
card above the panels and act on all of them at once through the shared view
and shapes stores, the same route a zoom dragged out on one panel takes to
reach the others.

A *tool* is a plotly ``dragmode`` (what a drag on a panel does) and is
persistent: the active one is whatever the shared view's ``dragmode`` holds.
An *action* runs once when clicked (zoom in, zoom out, erase the box). Both
are pattern ids answered by the toolbox callbacks. The two panel-set buttons,
reset and add, share the row but carry plain ids: they are answered by the
inspector's figure-building and panel-adding callbacks.
"""

from dataclasses import dataclass
from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.view_sync import ensure_view

TOOLBOX_TITLE = "Image Panel Tools"


@dataclass(frozen=True)
class imageButton:
    id: str  # for a tool, doubles as the plotly dragmode
    label: str
    icon: str
    tooltip: str


TOOLS: tuple[imageButton, ...] = (
    imageButton(
        "drawrect",
        "Draw box",
        "fa-solid fa-vector-square",
        "Drag out a box: the spectrum sums over the pixels inside it",
    ),
    imageButton(
        "zoom", "Zoom", "fa-solid fa-magnifying-glass", "Drag out a box to zoom into"
    ),
    imageButton("pan", "Pan", "fa-solid fa-hand", "Drag to move the view"),
)

ACTIONS: tuple[imageButton, ...] = (
    imageButton(
        "zoomin",
        "Zoom in",
        "fa-solid fa-magnifying-glass-plus",
        "Zoom in on the centre",
    ),
    imageButton(
        "zoomout",
        "Zoom out",
        "fa-solid fa-magnifying-glass-minus",
        "Zoom out from the centre",
    ),
    imageButton("eraseshape", "Erase box", "fa-solid fa-eraser", "Remove the box"),
)

RESET_IMAGES = imageButton(
    "reset",
    "Reset Extent",
    "fa-solid fa-rotate-left",
    "Zoom out to full extent on every panel",
)
ADD_IMAGE = imageButton("add", "Add Image", "fa-solid fa-plus", "Open another panel")

# The row, left to right; the buttons of a group sit flush against each other.
# Every tool and action appears in exactly one group. The add button is in no
# group: it sits alone at the right end of the row.
BUTTON_GROUPS: tuple[tuple[str, ...], ...] = (
    ("drawrect", "eraseshape"),
    ("zoom", "pan"),
    ("zoomin", "zoomout", RESET_IMAGES.id),
)

# what get_new_im puts on a fresh figure, and so what a view without a dragmode
# means
DEFAULT_TOOL = "drawrect"

TOOL_IDS = tuple(tool.id for tool in TOOLS)
ACTION_IDS = tuple(action.id for action in ACTIONS)
_BUTTONS = {button.id: button for button in (*TOOLS, *ACTIONS, RESET_IMAGES, ADD_IMAGE)}

# plotly's own zoom in / zoom out buttons halve and double the ranges
ZOOM_FACTORS = {"zoomin": 0.5, "zoomout": 2.0}


class imageToolboxLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = ("div", "tool", "action", "reset", "add")

    def __init__(self, id_type_base: str = "image-toolbox") -> None:
        super().__init__(id_type_base, None)

    @property
    def tool(self) -> str:
        return self.full_id("-tool")

    @property
    def action(self) -> str:
        return self.full_id("-action")

    @property
    def reset(self) -> str:
        return self.full_id("-reset")

    @property
    def add(self) -> str:
        return self.full_id("-add")

    def tool_id(self, tool: str) -> dict[str, str]:
        """The pattern-matching id of a tool button, indexed by the tool."""
        return {"type": self.tool, "index": tool}

    def action_id(self, action: str) -> dict[str, str]:
        return {"type": self.action, "index": action}

    def button_id(self, button: str) -> str | dict[str, str]:
        """The id of any toolbox button, pattern or plain."""
        if button in TOOL_IDS:
            return self.tool_id(button)
        if button in ACTION_IDS:
            return self.action_id(button)
        if button == RESET_IMAGES.id:
            return self.reset
        if button == ADD_IMAGE.id:
            return self.add
        msg = f"{button!r} is not a toolbox button"
        raise KeyError(msg)


def active_tool(view: dict[str, Any] | None) -> str:
    """The tool the shared view holds; no dragmode means the default."""
    dragmode = ensure_view(view)["dragmode"]
    return dragmode if isinstance(dragmode, str) else DEFAULT_TOOL


def tool_button_states(view: dict[str, Any] | None) -> list[bool]:
    """``active`` for each tool button, in TOOLS order."""
    current = active_tool(view)
    return [tool.id == current for tool in TOOLS]


def _icon_button(
    ids: imageToolboxLayoutIDs,
    button: str,
    *,
    active: bool = False,
    class_name: str = "",
    **kwargs: Any,
) -> dbc.Button:
    spec = _BUTTONS[button]
    return dbc.Button(
        [html.I(className=f"{spec.icon} me-1"), spec.label],
        id=ids.button_id(button),
        n_clicks=0,
        color="secondary",
        outline=True,
        active=active,
        className=f"text-nowrap {class_name}".strip(),
        **kwargs,
    )


def image_toolbox_layout(
    id_type_base: str = "image-toolbox",
) -> tuple[dbc.Card, imageToolboxLayoutIDs]:
    ids = imageToolboxLayoutIDs(id_type_base=id_type_base)
    pressed = active_tool(None)

    groups = [
        dbc.ButtonGroup(
            [_icon_button(ids, button, active=button == pressed) for button in group],
            size="sm",
        )
        for group in BUTTON_GROUPS
    ]
    add_button = _icon_button(ids, ADD_IMAGE.id, size="sm", class_name="ms-auto")
    tooltips = [
        dbc.Tooltip(spec.tooltip, target=ids.button_id(spec.id), placement="bottom")
        for spec in _BUTTONS.values()
    ]

    card = dbc.Card(
        [
            dbc.CardHeader(TOOLBOX_TITLE, className="px-2 py-1"),
            dbc.CardBody(
                [
                    html.Div(
                        [*groups, add_button],
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

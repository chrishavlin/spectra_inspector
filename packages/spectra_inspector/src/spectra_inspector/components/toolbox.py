"""The shared pieces of the plot toolboxes.

A toolbox is a card of labelled rows of buttons next to one or more plotly
graphs whose own modebars are switched off. Two kinds of button carry pattern
ids answered by wildcard callbacks: a *tool* is a plotly ``dragmode`` (what a
drag on the graph does) and is persistent, the pressed one following a store;
an *action* runs once when clicked. Any other button is *plain*: a plain id
and a callback of its own.

The image toolbox and the spectrum toolbox each declare a ``toolboxSpec`` and
call ``toolbox_card``; the callbacks are theirs. Nothing here talks to Dash
beyond building components.
"""

from dataclasses import dataclass
from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper


@dataclass(frozen=True)
class toolButton:
    id: str  # for a tool, doubles as the plotly dragmode
    label: str
    icon: str
    tooltip: str


@dataclass(frozen=True)
class toolboxRow:
    label: str
    tooltip: str
    # left to right; the buttons of a group sit flush against each other. A
    # row may hold no buttons at all and carry only the extras given at layout.
    groups: tuple[tuple[str, ...], ...] = ()


# the view controls both toolboxes offer; a toolbox may ``replace`` a tooltip
ZOOM = toolButton(
    "zoom", "Zoom", "fa-solid fa-magnifying-glass", "Drag out a box to zoom into"
)
PAN = toolButton("pan", "Pan", "fa-solid fa-hand", "Drag to move the view")
ZOOM_IN = toolButton(
    "zoomin", "Zoom in", "fa-solid fa-magnifying-glass-plus", "Zoom in on the centre"
)
ZOOM_OUT = toolButton(
    "zoomout",
    "Zoom out",
    "fa-solid fa-magnifying-glass-minus",
    "Zoom out from the centre",
)
RESET_EXTENT = toolButton(
    "reset", "Reset Extent", "fa-solid fa-rotate-left", "Zoom out to the full extent"
)

# plotly's own zoom in / zoom out buttons halve and double the ranges
ZOOM_FACTORS = {ZOOM_IN.id: 0.5, ZOOM_OUT.id: 2.0}

# the toggle of a collapsed toolbox; assets/toolbox.js flips between the two
CHEVRON_CLOSED = "fa-solid fa-chevron-down me-1"
CHEVRON_OPEN = "fa-solid fa-chevron-up me-1"


class toolboxLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "tool",
        "action",
        "row",
        "collapse",
        "toggle",
        "chevron",
    )

    def __init__(
        self, id_type_base: str, tools: tuple[str, ...], actions: tuple[str, ...]
    ) -> None:
        super().__init__(id_type_base, None)
        self.tools = tools
        self.actions = actions

    @property
    def tool(self) -> str:
        return self.full_id("-tool")

    @property
    def action(self) -> str:
        return self.full_id("-action")

    @property
    def row(self) -> str:
        return self.full_id("-row")

    @property
    def collapse(self) -> str:
        return self.full_id("-collapse")

    @property
    def toggle(self) -> str:
        return self.full_id("-toggle")

    @property
    def chevron(self) -> str:
        return self.full_id("-chevron")

    def tool_id(self, tool: str) -> dict[str, str]:
        """The pattern-matching id of a tool button, indexed by the tool."""
        return {"type": self.tool, "index": tool}

    def action_id(self, action: str) -> dict[str, str]:
        return {"type": self.action, "index": action}

    def row_id(self, position: int) -> dict[str, str | int]:
        """The id of a row's label, indexed by the row's position."""
        return {"type": self.row, "index": position}

    def button_id(self, button: str) -> str | dict[str, str]:
        """The id of any toolbox button: a pattern id for a tool or an action,
        a plain ``<base>-<button>`` id for anything else."""
        if button in self.tools:
            return self.tool_id(button)
        if button in self.actions:
            return self.action_id(button)
        return self.full_id(f"-{button}")


@dataclass(frozen=True)
class toolboxSpec:
    id_type_base: str
    title: str
    tools: tuple[toolButton, ...]
    actions: tuple[toolButton, ...]
    plain: tuple[toolButton, ...]
    rows: tuple[toolboxRow, ...]
    default_tool: str  # what a freshly built figure has as its dragmode

    def __post_init__(self) -> None:
        grouped = [
            button for row in self.rows for group in row.groups for button in group
        ]
        unknown = sorted(set(grouped) - set(self.buttons))
        if unknown:
            msg = f"{self.id_type_base}: rows name unknown buttons {unknown}"
            raise ValueError(msg)
        for button in (*self.tool_ids, *self.action_ids):
            if grouped.count(button) != 1:
                msg = f"{self.id_type_base}: {button!r} must appear in exactly one row"
                raise ValueError(msg)
        if self.default_tool not in self.tool_ids:
            msg = (
                f"{self.id_type_base}: default tool {self.default_tool!r} is not a tool"
            )
            raise ValueError(msg)

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return tuple(tool.id for tool in self.tools)

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(action.id for action in self.actions)

    @property
    def buttons(self) -> dict[str, toolButton]:
        return {b.id: b for b in (*self.tools, *self.actions, *self.plain)}

    @property
    def ids(self) -> toolboxLayoutIDs:
        return toolboxLayoutIDs(self.id_type_base, self.tool_ids, self.action_ids)

    def active_tool(self, view: dict[str, Any] | None) -> str:
        """The tool a view store holds; no dragmode means the default."""
        dragmode = (view or {}).get("dragmode")
        return dragmode if isinstance(dragmode, str) else self.default_tool

    def tool_button_states(self, view: dict[str, Any] | None) -> list[bool]:
        """``active`` for each tool button, in ``tools`` order."""
        current = self.active_tool(view)
        return [tool.id == current for tool in self.tools]

    def tool_states_for(
        self, view: dict[str, Any] | None, button_ids: list[dict[str, Any]]
    ) -> list[bool]:
        """``active`` for the tool buttons a wildcard callback reports, in
        the order it reports them."""
        states = dict(zip(self.tool_ids, self.tool_button_states(view), strict=True))
        return [states.get(button_id["index"], False) for button_id in button_ids]


def icon_button(
    spec: toolboxSpec,
    button: str,
    *,
    active: bool = False,
    class_name: str = "",
    **kwargs: Any,
) -> dbc.Button:
    ids = spec.ids
    detail = spec.buttons[button]
    return dbc.Button(
        [html.I(className=f"{detail.icon} me-1"), detail.label],
        id=ids.button_id(button),
        n_clicks=0,
        color="secondary",
        outline=True,
        active=active,
        className=f"text-nowrap {class_name}".strip(),
        **kwargs,
    )


def _row(spec: toolboxSpec, position: int, extras: list[Any]) -> html.Div:
    row = spec.rows[position]
    pressed = spec.active_tool(None)
    groups = [
        dbc.ButtonGroup(
            [icon_button(spec, button, active=button == pressed) for button in group],
            size="sm",
        )
        for group in row.groups
    ]
    label = html.Span(
        row.label,
        id=spec.ids.row_id(position),
        className="si-toolbox-label small fw-semibold text-nowrap",
    )
    return html.Div(
        [label, *groups, *extras],
        className="d-flex flex-wrap align-items-center gap-2",
    )


def toolbox_card(
    spec: toolboxSpec, extras: dict[int, list[Any]] | None = None
) -> dbc.Card:
    """The toolbox as a card: the title, then one labelled row per entry of
    ``spec.rows``. ``extras`` adds ready-made components to the end of a row,
    keyed by the row's position (a button that sits alone, a switch, ...)."""
    extras = extras or {}
    ids = spec.ids
    rows = [
        _row(spec, position, extras.get(position, []))
        for position in range(len(spec.rows))
    ]
    tooltips = [
        dbc.Tooltip(detail.tooltip, target=ids.button_id(button), placement="bottom")
        for button, detail in spec.buttons.items()
    ] + [
        dbc.Tooltip(row.tooltip, target=ids.row_id(position), placement="right")
        for position, row in enumerate(spec.rows)
    ]
    return dbc.Card(
        [
            dbc.CardHeader(spec.title, className="px-2 py-1"),
            dbc.CardBody(
                [html.Div(rows, className="d-flex flex-column gap-2"), *tooltips],
                className="p-2",
            ),
        ],
        id=ids.div,
        className="si-toolbox mb-2",
    )


def toolbox_collapse(
    spec: toolboxSpec, card: dbc.Card, label: str, *, is_open: bool = False
) -> tuple[dbc.Button, dbc.Collapse]:
    """A toggle button and the collapse it opens, for a toolbox that is
    hidden until asked for. Wiring the click up is the page's job (the
    ``toggleCollapse`` clientside function in ``assets/toolbox.js``)."""
    ids = spec.ids
    chevron = CHEVRON_OPEN if is_open else CHEVRON_CLOSED
    toggle = dbc.Button(
        [html.I(id=ids.chevron, className=chevron), label],
        id=ids.toggle,
        n_clicks=0,
        size="sm",
        color="secondary",
        outline=True,
        className="text-nowrap",
    )
    return toggle, dbc.Collapse(card, id=ids.collapse, is_open=is_open)

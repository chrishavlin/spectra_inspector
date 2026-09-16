import dash_bootstrap_components as dbc
import plotly.express as px
from dash import html

from spectra_inspector.components.image_toolbox import (
    ACTION_IDS,
    ACTIONS,
    ADD_IMAGE,
    DEFAULT_TOOL,
    RESET_IMAGES,
    ROWS,
    TOOL_IDS,
    TOOLBOX_TITLE,
    TOOLS,
    ZOOM_FACTORS,
    active_tool,
    image_toolbox_layout,
    tool_button_states,
)
from spectra_inspector.utilities.view_sync import empty_view


def _find(component, predicate, found=None):
    found = [] if found is None else found
    if predicate(component):
        found.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, list):
        for child in children:
            _find(child, predicate, found)
    elif children is not None and not isinstance(children, str):
        _find(children, predicate, found)
    return found


def test_image_toolbox_layout_ids():
    _, ids = image_toolbox_layout()
    for prop in ids.prop_names:
        assert prop in getattr(ids, prop)
    assert ids.tool_id("zoom") == {"type": ids.tool, "index": "zoom"}
    assert ids.action_id("zoomin") == {"type": ids.action, "index": "zoomin"}
    assert ids.row_id(1) == {"type": ids.row, "index": 1}
    assert len({ids.tool, ids.action, ids.reset, ids.add, ids.row}) == 5
    assert ids.button_id("zoom") == ids.tool_id("zoom")
    assert ids.button_id("eraseshape") == ids.action_id("eraseshape")
    assert ids.button_id(RESET_IMAGES.id) == ids.reset
    assert ids.button_id(ADD_IMAGE.id) == ids.add


def test_rows_cover_every_tool_and_action_once():
    grouped = [button for row in ROWS for group in row.groups for button in group]
    assert sorted(grouped) == sorted((*TOOL_IDS, *ACTION_IDS, RESET_IMAGES.id))
    assert ADD_IMAGE.id not in grouped
    assert len({row.label for row in ROWS}) == len(ROWS)


def test_layout_is_labelled_rows_with_add_at_the_top_right():
    card, ids = image_toolbox_layout()
    rows = _find(card, lambda c: isinstance(c, html.Div) and "flex-wrap" in c.className)
    assert len(rows) == len(ROWS)
    for position, (row, spec) in enumerate(zip(rows, ROWS, strict=True)):
        label, *groups = row.children
        assert label.children == spec.label
        assert label.id == ids.row_id(position)
        if position == 0:
            *groups, add_button = groups
            assert add_button.id == ids.add
            assert "ms-auto" in add_button.className
        assert all(isinstance(group, dbc.ButtonGroup) for group in groups)
        assert [[button.id for button in group.children] for group in groups] == [
            [ids.button_id(button) for button in group] for group in spec.groups
        ]

    buttons = _find(card, lambda c: isinstance(c, dbc.Button))
    assert len(buttons) == sum(len(g) for row in ROWS for g in row.groups) + 1
    # only the default tool starts pressed
    pressed = [button.id for button in buttons if button.active]
    assert pressed == [ids.tool_id(DEFAULT_TOOL)]

    tooltips = _find(card, lambda c: isinstance(c, dbc.Tooltip))
    targets = sorted(map(str, (t.target for t in tooltips)))
    labelled = [b.id for b in buttons] + [ids.row_id(i) for i in range(len(ROWS))]
    assert targets == sorted(map(str, labelled))
    headers = _find(card, lambda c: isinstance(c, dbc.CardHeader))
    assert headers[0].children == TOOLBOX_TITLE


def test_tools_are_plotly_dragmodes():
    # a tool id is set on the figures as-is
    fig = px.imshow([[1, 2], [3, 4]])
    for tool in TOOL_IDS:
        fig.update_layout(dragmode=tool)
    assert DEFAULT_TOOL in TOOL_IDS


def test_every_action_is_handled():
    for action in ACTIONS:
        assert action.id == "eraseshape" or action.id in ZOOM_FACTORS


def test_active_tool_follows_the_view():
    assert active_tool(None) == DEFAULT_TOOL
    assert active_tool(empty_view()) == DEFAULT_TOOL
    assert active_tool({"dragmode": "pan"}) == "pan"
    assert tool_button_states({"dragmode": "zoom"}) == [t.id == "zoom" for t in TOOLS]
    # a dragmode no button owns presses nothing
    assert not any(tool_button_states({"dragmode": "select"}))

import dash_bootstrap_components as dbc
import plotly.express as px

from spectra_inspector.components.image_toolbox import (
    ACTION_IDS,
    ACTIONS,
    DEFAULT_TOOL,
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
    assert ids.tool != ids.action


def test_layout_has_a_button_per_tool_and_action():
    card, ids = image_toolbox_layout()
    buttons = _find(card, lambda c: isinstance(c, dbc.Button))
    button_ids = [button.id for button in buttons]
    assert [ids.tool_id(tool) for tool in TOOL_IDS] == button_ids[: len(TOOLS)]
    assert [ids.action_id(action) for action in ACTION_IDS] == button_ids[len(TOOLS) :]
    # only the default tool starts pressed
    pressed = [button.id["index"] for button in buttons if button.active]
    assert pressed == [DEFAULT_TOOL]
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

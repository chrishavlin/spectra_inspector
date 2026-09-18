import dash_bootstrap_components as dbc
import plotly.express as px
from dash import html

from spectra_inspector.components.image_toolbox import (
    ADD_IMAGE,
    DRAW_BOX,
    ERASE_BOX,
    IMAGE_TOOLBOX,
    PANEL_MODE_ROW,
    image_toolbox_layout,
)
from spectra_inspector.components.tests.test_toolbox import find, rows_of
from spectra_inspector.components.toolbox import ZOOM_FACTORS
from spectra_inspector.utilities.view_sync import empty_view


def test_ids_are_the_page_wide_spellings():
    ids = IMAGE_TOOLBOX.ids
    assert ids.div == "image-toolbox-div"
    assert ids.tool == "image-toolbox-tool"
    assert ids.action == "image-toolbox-action"
    assert ids.button_id(ADD_IMAGE.id) == "image-toolbox-add"
    assert ids.button_id("reset") == "image-toolbox-reset"


def test_rows():
    first, second, third = IMAGE_TOOLBOX.rows
    assert first.label == "Extract Spectrum"
    assert first.groups == ((DRAW_BOX.id, ERASE_BOX.id),)
    assert second.label == "View Controls"
    assert second.groups == (("zoom", "pan"), ("zoomin", "zoomout", "reset"))
    assert third.label == "Panel Mode"
    assert third.groups == ()
    assert IMAGE_TOOLBOX.rows[PANEL_MODE_ROW] is third
    grouped = [b for row in IMAGE_TOOLBOX.rows for g in row.groups for b in g]
    assert ADD_IMAGE.id not in grouped


def test_layout_puts_add_at_the_right_of_the_first_row():
    card, ids = image_toolbox_layout()
    assert ids.div == IMAGE_TOOLBOX.ids.div
    rows = rows_of(card)
    assert len(rows) == 3
    add_button = rows[0].children[-1]
    assert add_button.id == ids.button_id(ADD_IMAGE.id)
    assert "ms-auto" in add_button.className
    assert isinstance(rows[1].children[-1], dbc.ButtonGroup)
    buttons = find(card, lambda c: isinstance(c, dbc.Button))
    assert len(buttons) == 8
    pressed = [b.id for b in buttons if b.active]
    assert pressed == [ids.tool_id(DRAW_BOX.id)]


def test_layout_fills_the_panel_mode_row_with_the_switch():
    switch = html.Div(id="mode-switch", className="")
    card, _ = image_toolbox_layout([switch])
    rows = rows_of(card)
    assert rows[PANEL_MODE_ROW].children[-1] is switch
    # the label alone when nothing is passed
    card, _ = image_toolbox_layout()
    assert len(rows_of(card)[PANEL_MODE_ROW].children) == 1


def test_tools_are_plotly_dragmodes():
    # a tool id is set on the figures as-is
    fig = px.imshow([[1, 2], [3, 4]])
    for tool in IMAGE_TOOLBOX.tool_ids:
        fig.update_layout(dragmode=tool)


def test_every_action_is_handled():
    for action in IMAGE_TOOLBOX.action_ids:
        assert action == ERASE_BOX.id or action in ZOOM_FACTORS


def test_default_tool_follows_the_view():
    assert IMAGE_TOOLBOX.active_tool(None) == DRAW_BOX.id
    assert IMAGE_TOOLBOX.active_tool(empty_view()) == DRAW_BOX.id
    assert IMAGE_TOOLBOX.active_tool({"dragmode": "pan"}) == "pan"

import dash_bootstrap_components as dbc
import plotly.express as px
from dash import html

from spectra_inspector.components.image_toolbox import (
    ADD_IMAGE,
    DRAW_BOX,
    DRAW_POLYGON,
    ERASE_SHAPE,
    IMAGE_TOOLBOX,
    PANEL_MODE_ROW,
    POLYGON_CONTROLS_ID,
    POLYGON_INSTRUCTIONS,
    POLYGON_NOTE_ID,
    SCALEBAR_COLOR_ID,
    SCALEBAR_FONTSIZE_ID,
    SCALEBAR_ROW,
    SCALEBAR_SHOW_ID,
    SUBMIT_SHAPE,
    image_toolbox_layout,
)
from spectra_inspector.components.tests.test_toolbox import find, rows_of
from spectra_inspector.components.toolbox import ZOOM_FACTORS
from spectra_inspector.utilities.scalebar_style import (
    DEFAULT_SCALEBAR_COLOR,
    DEFAULT_SCALEBAR_FONTSIZE,
    MAX_SCALEBAR_FONTSIZE,
    MIN_SCALEBAR_FONTSIZE,
)
from spectra_inspector.utilities.view_sync import POLYGON_TOOL, empty_view, tool_layout


def test_ids_are_the_page_wide_spellings():
    ids = IMAGE_TOOLBOX.ids
    assert ids.div == "image-toolbox-div"
    assert ids.tool == "image-toolbox-tool"
    assert ids.action == "image-toolbox-action"
    assert ids.button_id(ADD_IMAGE.id) == "image-toolbox-add"
    assert ids.button_id("reset") == "image-toolbox-reset"
    assert ids.button_id(SUBMIT_SHAPE.id) == "image-toolbox-submit"
    assert POLYGON_CONTROLS_ID == "image-toolbox-polygon-controls"


def test_rows():
    first, second, third, fourth = IMAGE_TOOLBOX.rows
    assert first.label == "Extract Spectrum"
    assert first.groups == ((DRAW_BOX.id, DRAW_POLYGON.id, ERASE_SHAPE.id),)
    assert second.label == "View Controls"
    assert second.groups == (("zoom", "pan"), ("zoomin", "zoomout", "reset"))
    assert third.label == "Scalebar"
    assert third.groups == ()
    assert IMAGE_TOOLBOX.rows[SCALEBAR_ROW] is third
    assert fourth.label == "Panel Mode"
    assert fourth.groups == ()
    assert IMAGE_TOOLBOX.rows[PANEL_MODE_ROW] is fourth
    grouped = [b for row in IMAGE_TOOLBOX.rows for g in row.groups for b in g]
    assert ADD_IMAGE.id not in grouped
    assert SUBMIT_SHAPE.id not in grouped


def test_layout_fills_the_scalebar_row_with_its_controls():
    card, _ = image_toolbox_layout()
    row = rows_of(card)[SCALEBAR_ROW]
    (show,) = find(row, lambda c: getattr(c, "id", None) == SCALEBAR_SHOW_ID)
    (color,) = find(row, lambda c: getattr(c, "id", None) == SCALEBAR_COLOR_ID)
    (size,) = find(row, lambda c: getattr(c, "id", None) == SCALEBAR_FONTSIZE_ID)
    # drawn by default, in the shared default colour and label size
    assert isinstance(show, dbc.Checkbox)
    assert show.value is True
    assert color.type == "color"
    assert color.value == DEFAULT_SCALEBAR_COLOR
    assert size.type == "number"
    assert size.value == DEFAULT_SCALEBAR_FONTSIZE
    assert (size.min, size.max) == (MIN_SCALEBAR_FONTSIZE, MAX_SCALEBAR_FONTSIZE)
    # plain ids, so the page's callbacks can name them
    assert SCALEBAR_SHOW_ID.startswith(IMAGE_TOOLBOX.ids.id_type_base)


def test_layout_puts_add_at_the_right_of_the_first_row():
    card, ids = image_toolbox_layout()
    assert ids.div == IMAGE_TOOLBOX.ids.div
    rows = rows_of(card)
    assert len(rows) == 4
    add_button = rows[0].children[-2]
    assert add_button.id == ids.button_id(ADD_IMAGE.id)
    assert "ms-auto" in add_button.className
    assert isinstance(rows[1].children[-1], dbc.ButtonGroup)
    buttons = find(card, lambda c: isinstance(c, dbc.Button))
    assert len(buttons) == 10
    pressed = [b.id for b in buttons if b.active]
    assert pressed == [ids.tool_id(DRAW_BOX.id)]


def test_polygon_controls_sit_hidden_before_add_and_the_note_below():
    card, ids = image_toolbox_layout()
    rows = rows_of(card)
    controls = rows[0].children[-3]
    assert controls.id == POLYGON_CONTROLS_ID
    assert controls.hidden is True
    submit = controls.children
    assert submit.id == ids.button_id(SUBMIT_SHAPE.id)
    assert submit.disabled is True
    # the note is the row's last item and full width, so the row wraps it
    # onto a line of its own under the buttons
    note = rows[0].children[-1]
    assert note.id == POLYGON_NOTE_ID
    assert note.hidden is True
    assert "w-100" in note.className
    assert note.children == POLYGON_INSTRUCTIONS
    assert "double click" in POLYGON_INSTRUCTIONS
    # no bootstrap display class on the hidden elements: those are
    # !important and would override the hidden attribute
    for hidden in (controls, note):
        assert "d-" not in hidden.className


def test_layout_fills_the_panel_mode_row_with_the_switch():
    switch = html.Div(id="mode-switch", className="")
    card, _ = image_toolbox_layout([switch])
    rows = rows_of(card)
    assert rows[PANEL_MODE_ROW].children[-1] is switch
    # the label alone when nothing is passed
    card, _ = image_toolbox_layout()
    assert len(rows_of(card)[PANEL_MODE_ROW].children) == 1


def test_tools_have_a_plotly_layout():
    # every tool's layout is accepted by plotly; only the polygon tool is not
    # a dragmode itself, it switches dragging off and fixes the axes
    fig = px.imshow([[1, 2], [3, 4]])
    for tool in IMAGE_TOOLBOX.tool_ids:
        fig.update_layout(tool_layout(tool))
        if tool == POLYGON_TOOL:
            assert fig.layout.dragmode is False
            assert fig.layout.xaxis.fixedrange is True
            assert fig.layout.yaxis.fixedrange is True
        else:
            assert fig.layout.dragmode == tool
            assert fig.layout.xaxis.fixedrange is False
    assert DRAW_POLYGON.id == POLYGON_TOOL


def test_every_action_is_handled():
    for action in IMAGE_TOOLBOX.action_ids:
        assert action == ERASE_SHAPE.id or action in ZOOM_FACTORS


def test_default_tool_follows_the_view():
    assert IMAGE_TOOLBOX.active_tool(None) == DRAW_BOX.id
    assert IMAGE_TOOLBOX.active_tool(empty_view()) == DRAW_BOX.id
    assert IMAGE_TOOLBOX.active_tool({"dragmode": "pan"}) == "pan"
    assert IMAGE_TOOLBOX.active_tool({"dragmode": POLYGON_TOOL}) == POLYGON_TOOL

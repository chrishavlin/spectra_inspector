import dash_bootstrap_components as dbc
from dash import html

from spectra_inspector.components.image_toolbox import IMAGE_TOOLBOX
from spectra_inspector.components.spectrum_toolbox import (
    DISPLAY_ROW,
    SPECTRUM_TOOLBOX,
    TOGGLE_LABEL,
    spectrum_toolbox_layout,
)
from spectra_inspector.components.tests.test_toolbox import find, rows_of
from spectra_inspector.components.toolbox import CHEVRON_CLOSED, ZOOM_FACTORS


def test_ids_do_not_collide_with_the_image_toolbox():
    ids = SPECTRUM_TOOLBOX.ids
    assert ids.tool == "spectrum-toolbox-tool"
    assert ids.action == "spectrum-toolbox-action"
    assert ids.button_id("reset") == "spectrum-toolbox-reset"
    image = IMAGE_TOOLBOX.ids
    assert {ids.tool, ids.action, ids.div}.isdisjoint(
        {image.tool, image.action, image.div}
    )


def test_view_controls_only():
    assert SPECTRUM_TOOLBOX.tool_ids == ("zoom", "pan")
    assert "drawrect" not in SPECTRUM_TOOLBOX.tool_ids
    assert SPECTRUM_TOOLBOX.action_ids == ("zoomin", "zoomout")
    assert all(action in ZOOM_FACTORS for action in SPECTRUM_TOOLBOX.action_ids)
    assert "add" not in SPECTRUM_TOOLBOX.buttons
    # plotly's own default, what a fresh go.Figure gets
    assert SPECTRUM_TOOLBOX.default_tool == "zoom"


def test_layout_is_a_closed_collapse_holding_the_display_controls():
    switch = html.Span("switch", id="switch")
    radio = html.Span("radio", id="radio")
    toggle, collapse, ids = spectrum_toolbox_layout([switch, radio])

    assert collapse.is_open is False
    assert collapse.id == ids.collapse
    assert toggle.id == ids.toggle
    chevron, label = toggle.children
    assert chevron.className == CHEVRON_CLOSED
    assert label == TOGGLE_LABEL

    rows = rows_of(collapse)
    assert len(rows) == 2
    view_label, *groups = rows[0].children
    assert view_label.children == "View Controls"
    assert [[b.id for b in g.children] for g in groups] == [
        [ids.tool_id("zoom"), ids.tool_id("pan")],
        [ids.action_id("zoomin"), ids.action_id("zoomout"), ids.button_id("reset")],
    ]
    display_label, *controls = rows[DISPLAY_ROW].children
    assert display_label.children == "Display"
    assert controls == [switch, radio]

    buttons = find(collapse, lambda c: isinstance(c, dbc.Button))
    assert len(buttons) == 5
    pressed = [b.id for b in buttons if b.active]
    assert pressed == [ids.tool_id("zoom")]

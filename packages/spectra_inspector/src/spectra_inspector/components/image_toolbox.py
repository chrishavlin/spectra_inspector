"""One toolbar for every image panel.

The tools act on all the panels at once through the shared view and shapes
stores, the same route a zoom dragged out on one panel takes to reach the
others; the pressed tool is whatever the shared view's ``dragmode`` holds. The
two plain buttons, reset and add, are answered by the inspector's
figure-building and panel-adding callbacks, and the Panel Mode row holds the
page's single / multi-channel switch, passed in ready-made. The polygon tool
brings its own controls into the first row: a note on how to place points and
the Submit shape button that sends the finished polygon to the server. See
``components/toolbox.py`` for the pieces shared with the spectrum's toolbox.
"""

from dataclasses import replace
from typing import Any

import dash_bootstrap_components as dbc
from dash import html

from spectra_inspector.components.toolbox import (
    PAN,
    RESET_EXTENT,
    ZOOM,
    ZOOM_IN,
    ZOOM_OUT,
    icon_button,
    toolbox_card,
    toolboxLayoutIDs,
    toolboxRow,
    toolboxSpec,
    toolButton,
)
from spectra_inspector.utilities.view_sync import POLYGON_TOOL

DRAW_BOX = toolButton(
    "drawrect",
    "Draw box",
    "fa-solid fa-vector-square",
    "Drag out a box: the spectrum sums over the pixels inside it",
)
DRAW_POLYGON = toolButton(
    POLYGON_TOOL,
    "Draw shape",
    "fa-solid fa-draw-polygon",
    "Click on a panel to place the corners of a shape, drag them into place, "
    "then Submit shape",
)
ERASE_SHAPE = toolButton(
    "eraseshape", "Erase shape", "fa-solid fa-eraser", "Remove the box or shape"
)
SUBMIT_SHAPE = toolButton(
    "submit",
    "Submit shape",
    "fa-solid fa-check",
    "Sum the spectrum over the pixels inside the shape",
)
RESET_IMAGES = replace(RESET_EXTENT, tooltip="Zoom out to full extent on every panel")
ADD_IMAGE = toolButton("add", "Add Image", "fa-solid fa-plus", "Open another panel")

POLYGON_INSTRUCTIONS = (
    "Click on an image to add a corner after the red end of your selection "
    "path (green is its start), drag a corner to move it, double click a "
    "corner to remove it or a line segment to insert a corner there, then "
    "Submit shape."
)

IMAGE_TOOLBOX = toolboxSpec(
    id_type_base="image-toolbox",
    title="Image Panel Tools",
    tools=(DRAW_BOX, DRAW_POLYGON, ZOOM, PAN),
    actions=(ZOOM_IN, ZOOM_OUT, ERASE_SHAPE),
    plain=(RESET_IMAGES, ADD_IMAGE, SUBMIT_SHAPE),
    rows=(
        toolboxRow(
            "Extract Spectrum",
            "The spectrum below sums the pixels inside the selection",
            ((DRAW_BOX.id, DRAW_POLYGON.id, ERASE_SHAPE.id),),
        ),
        toolboxRow(
            "View Controls",
            "Zoom and pan every panel together",
            ((ZOOM.id, PAN.id), (ZOOM_IN.id, ZOOM_OUT.id, RESET_IMAGES.id)),
        ),
        toolboxRow(
            "Panel Mode",
            "One element map per panel, or one panel blending up to three maps",
        ),
    ),
    # what get_new_im puts on a fresh figure
    default_tool=DRAW_BOX.id,
)


# the row the page's mode switch is added to
PANEL_MODE_ROW = 2

# the polygon tool's controls: shown only while that tool is pressed
POLYGON_CONTROLS_ID = IMAGE_TOOLBOX.ids.full_id("-polygon-controls")
POLYGON_NOTE_ID = IMAGE_TOOLBOX.ids.full_id("-polygon-note")


def polygon_controls() -> html.Div:
    """Submit shape and the how-to note, hidden until the polygon tool is
    picked (``toggle_polygon_controls`` on the inspector page)."""
    submit = icon_button(IMAGE_TOOLBOX, SUBMIT_SHAPE.id, size="sm", disabled=True)
    note = html.Span(
        POLYGON_INSTRUCTIONS,
        id=POLYGON_NOTE_ID,
        className="small text-body-secondary",
    )
    # the display class sits on an inner div: bootstrap's ``d-*`` utilities
    # are !important and would override the ``hidden`` attribute
    return html.Div(
        html.Div([submit, note], className="d-inline-flex align-items-center gap-2"),
        id=POLYGON_CONTROLS_ID,
        hidden=True,
        className="si-polygon-controls",
    )


def image_toolbox_layout(
    mode_controls: list[Any] | None = None,
) -> tuple[dbc.Card, toolboxLayoutIDs]:
    """The card, with the polygon controls and then Add Image alone at the
    right end of the first row, and ``mode_controls`` filling the Panel Mode
    row."""
    add_button = icon_button(
        IMAGE_TOOLBOX, ADD_IMAGE.id, size="sm", class_name="ms-auto"
    )
    extras = {
        0: [polygon_controls(), add_button],
        PANEL_MODE_ROW: mode_controls or [],
    }
    return toolbox_card(IMAGE_TOOLBOX, extras=extras), IMAGE_TOOLBOX.ids

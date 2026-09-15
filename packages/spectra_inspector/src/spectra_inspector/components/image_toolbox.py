"""One toolbar for every image panel.

The tools act on all the panels at once through the shared view and shapes
stores, the same route a zoom dragged out on one panel takes to reach the
others; the pressed tool is whatever the shared view's ``dragmode`` holds. The
two plain buttons, reset and add, are answered by the inspector's
figure-building and panel-adding callbacks, and the Panel Mode row holds the
page's single / multi-channel switch, passed in ready-made. See
``components/toolbox.py`` for the pieces shared with the spectrum's toolbox.
"""

from dataclasses import replace
from typing import Any

import dash_bootstrap_components as dbc

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

DRAW_BOX = toolButton(
    "drawrect",
    "Draw box",
    "fa-solid fa-vector-square",
    "Drag out a box: the spectrum sums over the pixels inside it",
)
ERASE_BOX = toolButton(
    "eraseshape", "Erase box", "fa-solid fa-eraser", "Remove the box"
)
RESET_IMAGES = replace(RESET_EXTENT, tooltip="Zoom out to full extent on every panel")
ADD_IMAGE = toolButton("add", "Add Image", "fa-solid fa-plus", "Open another panel")

IMAGE_TOOLBOX = toolboxSpec(
    id_type_base="image-toolbox",
    title="Image Panel Tools",
    tools=(DRAW_BOX, ZOOM, PAN),
    actions=(ZOOM_IN, ZOOM_OUT, ERASE_BOX),
    plain=(RESET_IMAGES, ADD_IMAGE),
    rows=(
        toolboxRow(
            "Extract Spectrum",
            "The spectrum below sums the pixels inside the selection",
            ((DRAW_BOX.id, ERASE_BOX.id),),
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


def image_toolbox_layout(
    mode_controls: list[Any] | None = None,
) -> tuple[dbc.Card, toolboxLayoutIDs]:
    """The card, with Add Image alone at the right end of the first row and
    ``mode_controls`` filling the Panel Mode row."""
    add_button = icon_button(
        IMAGE_TOOLBOX, ADD_IMAGE.id, size="sm", class_name="ms-auto"
    )
    extras = {0: [add_button], PANEL_MODE_ROW: mode_controls or []}
    return toolbox_card(IMAGE_TOOLBOX, extras=extras), IMAGE_TOOLBOX.ids

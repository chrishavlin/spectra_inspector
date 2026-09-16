"""The spectrum plot's toolbar, folded away under the plot until asked for.

There is one spectrum graph and nothing to keep in step with it, so only the
tool (the dragmode) goes through the server, patched onto the figure and
remembered in a store so a rebuilt figure keeps it. The zoom steps and the
reset act on the plot's live ranges, which exist only in the browser (the
figure prop never receives a zoom): ``assets/toolbox.js`` relayouts them
clientside, and a zoom step scales the energy axis only, leaving the
intensity baseline where it is. The plot's display switches live in the
second row, passed in ready-made by the page. See ``components/toolbox.py``
for the pieces shared with the image panels' toolbox.
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
    toolbox_card,
    toolbox_collapse,
    toolboxLayoutIDs,
    toolboxRow,
    toolboxSpec,
)

SPECTRUM_ZOOM_IN = replace(ZOOM_IN, tooltip="Halve the energy range about its centre")
SPECTRUM_ZOOM_OUT = replace(
    ZOOM_OUT, tooltip="Double the energy range about its centre"
)
SPECTRUM_RESET = replace(RESET_EXTENT, tooltip="Back to the full spectrum")

# the row the page's display switches (peak windows, y scale) are added to
DISPLAY_ROW = 1

SPECTRUM_TOOLBOX = toolboxSpec(
    id_type_base="spectrum-toolbox",
    title="Spectrum Plot Tools",
    tools=(ZOOM, PAN),
    actions=(SPECTRUM_ZOOM_IN, SPECTRUM_ZOOM_OUT),
    plain=(SPECTRUM_RESET,),
    rows=(
        toolboxRow(
            "View Controls",
            "Zoom and pan the spectrum; a zoom step changes the energy range only",
            ((ZOOM.id, PAN.id), (ZOOM_IN.id, ZOOM_OUT.id, RESET_EXTENT.id)),
        ),
        toolboxRow("Display", "What the plot shows"),
    ),
    # plotly's own default, what go.Figure() starts with
    default_tool=ZOOM.id,
)

TOGGLE_LABEL = "Plot tools"


def spectrum_toolbox_layout(
    display_controls: list[Any],
) -> tuple[dbc.Button, dbc.Collapse, toolboxLayoutIDs]:
    """The toggle button, the collapse holding the card (closed to start
    with) and the ids. ``display_controls`` fill the Display row."""
    card = toolbox_card(SPECTRUM_TOOLBOX, extras={DISPLAY_ROW: display_controls})
    toggle, collapse = toolbox_collapse(SPECTRUM_TOOLBOX, card, TOGGLE_LABEL)
    return toggle, collapse, SPECTRUM_TOOLBOX.ids

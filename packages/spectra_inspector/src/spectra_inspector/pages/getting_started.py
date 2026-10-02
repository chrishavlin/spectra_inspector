import dash
from dash import dcc, html

from spectra_inspector.components.annotated_screenshot import (
    annotated_screenshot,
    screenshotMarker,
)

dash.register_page(__name__, name="Getting started", order=2)


DATA_SELECTION_MARKERS = [
    screenshotMarker(
        target=(305, 295),
        badge=(305, 170),
        description=[
            "Pick a sample from the ",
            html.B("Select a sample"),
            " dropdown.",
        ],
    ),
    screenshotMarker(
        target=(400, 222),
        badge=(560, 160),
        description=[
            "Turn on ",
            html.B("Spectrum only"),
            " to list individual spectrum (.spc) files instead of full EDAX "
            "sets. Switching modes clears the current selection.",
        ],
    ),
    screenshotMarker(
        target=(577, 348),
        badge=(577, 440),
        description="The refresh button rescans the server for new datasets.",
    ),
    screenshotMarker(
        target=(305, 440),
        badge=(420, 440),
        description=[html.B("Load Selected"), " opens the sample in the inspector."],
    ),
    screenshotMarker(
        target=(330, 935),
        badge=(330, 1080),
        description=(
            "The selected sample's metadata. Expand a section to see its details."
        ),
    ),
    screenshotMarker(
        target=(1245, 735),
        badge=(1110, 580),
        description=(
            "Each sample is a point on the map, at the location the rock "
            "was collected. Click a point to select that sample."
        ),
    ),
    screenshotMarker(
        target=(1108, 197),
        badge=(1220, 197),
        description="Switch the basemap between satellite, street and blank styles.",
    ),
]

TOOLBOX_MARKERS = [
    screenshotMarker(
        target=(605, 160),
        badge=(605, 97),
        description=[
            "The ",
            html.B("Sample"),
            " dropdown switches to another sample without going back to Data "
            "Selection. It has the same ",
            html.B("Spectrum only"),
            " switch and refresh button.",
        ],
    ),
    screenshotMarker(
        target=(967, 380),
        badge=(1080, 380),
        description=[
            html.B("Extract Spectrum:"),
            " with ",
            html.B("Draw box"),
            ", drag out a box on any panel and the spectrum below sums the "
            "pixels inside it. With ",
            html.B("Draw shape"),
            ", click to place the corners of a polygon (see below), then click ",
            html.B("Submit shape"),
            ", which appears next to the tools while drawing. ",
            html.B("Erase shape"),
            " removes the selection and returns to the full spectrum.",
        ],
    ),
    screenshotMarker(
        target=(1917, 380),
        badge=(1814, 380),
        description=[html.B("Add Image"), " opens another image panel."],
    ),
    screenshotMarker(
        target=(1212, 458),
        badge=(1318, 458),
        description=[
            html.B("View Controls:"),
            " ",
            html.B("Zoom"),
            " drags out a box to zoom into, ",
            html.B("Pan"),
            " drags the view, the zoom in / out buttons step about the centre, and ",
            html.B("Reset Extent"),
            " zooms back out to the full image.",
        ],
    ),
    screenshotMarker(
        target=(848, 536),
        badge=(950, 536),
        description=[
            html.B("Scalebar:"),
            " show or hide the scalebar and set its colour and text size. The "
            "same style is used on exported images.",
        ],
    ),
    screenshotMarker(
        target=(940, 621),
        badge=(1037, 621),
        description=[
            html.B("Panel Mode"),
            " switches between ",
            html.B("single channel"),
            " panels and one ",
            html.B("multi-channel"),
            " composite panel (see below).",
        ],
    ),
]

PANEL_MARKERS = [
    screenshotMarker(
        target=(269, 67),
        badge=(448, 67),
        description="Choose the element map a panel shows.",
    ),
    screenshotMarker(
        target=(224, 211),
        badge=(352, 352),
        description=[
            html.B("Adjust energy bounds"),
            " opens a slider to set a custom energy window (keV).",
        ],
    ),
    screenshotMarker(
        target=(838, 67),
        badge=(736, 67),
        description=[
            html.B("Apply"),
            " redraws the map with the new element or energy window; ",
            html.B("X"),
            " next to it removes the panel.",
        ],
    ),
    screenshotMarker(
        target=(811, 208),
        badge=(811, 352),
        description=["Pick a ", html.B("Colormap"), " for the panel."],
    ),
    screenshotMarker(
        target=(761, 587),
        badge=(907, 448),
        description=[
            "A shape drawn with ",
            html.B("Draw shape"),
            ". Click to add a corner after the red end of the path (green is "
            "its start), drag a corner to move it, and double click a corner "
            "to remove it or a line segment to insert a corner there.",
        ],
    ),
    screenshotMarker(
        target=(1652, 704),
        badge=(1387, 555),
        description=(
            "Every panel shows the same selection, zoom and pan, so drawing or "
            "zooming on one panel does the same on the others."
        ),
    ),
]

SPECTRUM_MARKERS = [
    screenshotMarker(
        target=(321, 603),
        badge=(360, 444),
        description=(
            "The spectrum of the whole sample, or of the current selection. "
            "Scroll over the plot to zoom."
        ),
    ),
    screenshotMarker(
        target=(555, 196),
        badge=(730, 116),
        description=(
            "Peak windows: the energy window used for each element's weight, "
            "labelled and coloured to match the element weights table."
        ),
    ),
    screenshotMarker(
        target=(1867, 982),
        badge=(1756, 982),
        description=[html.B("Plot tools"), " shows the spectrum's toolbox (below)."],
    ),
]

EXPORT_MARKERS = [
    screenshotMarker(
        target=(893, 288),
        badge=(999, 288),
        description=[
            html.B("Export summary"),
            " downloads the figures, element weights and sample metadata as a "
            ".zip or a PDF.",
        ],
    ),
    screenshotMarker(
        target=(893, 524),
        badge=(999, 524),
        description=[
            html.B("Export Spectrum"),
            " downloads the current spectrum as .msa or .csv, with intensity "
            "only (Y) or energy and intensity (XY) columns.",
        ],
    ),
    screenshotMarker(
        target=(1921, 524),
        badge=(1843, 524),
        description=(
            "The weight computed for each element. Click an element's ✕ "
            "to zero it out, which also drops its peak window from the "
            "spectrum, and its ↺ to restore it."
        ),
    ),
    screenshotMarker(
        target=(1936, 88),
        badge=(1832, 88),
        description=[html.B("Reset"), " restores every zeroed element."],
    ),
    screenshotMarker(
        target=(2016, 196),
        badge=(2016, 302),
        description="Copy the weights for pasting into a spreadsheet.",
    ),
]

# each screenshot in assets/getting_started/, by file stem: its size in pixels
# and its markers, in that image's pixel coordinates
SCREENSHOTS: dict[str, tuple[tuple[int, int], list[screenshotMarker]]] = {
    "data_selection": ((1932, 1420), DATA_SELECTION_MARKERS),
    "inspector_toolbox": ((2160, 688), TOOLBOX_MARKERS),
    "inspector_panels": ((2134, 1036), PANEL_MARKERS),
    "inspector_spectrum": ((2116, 1078), SPECTRUM_MARKERS),
    "inspector_export": ((2082, 1204), EXPORT_MARKERS),
}


def _screenshot(name: str, alt: str) -> html.Div:
    size, markers = SCREENSHOTS[name]
    src = dash.get_asset_url(f"getting_started/{name}.png")
    return annotated_screenshot(src, size, markers, alt=alt)


layout = html.Div(
    [
        html.H1("Getting started"),
        html.P(
            [
                "Spectra Inspector is a browser-based tool for exploring EDAX "
                "filesets: pick a sample, view its element maps, select a region "
                "of an image to extract the spectrum summed over it, and export "
                "the results. Most controls show a short description when you "
                "hover over them.",
            ]
        ),
        html.Hr(),
        html.H2("Data Selection"),
        html.P(
            [
                "Start on the ",
                dcc.Link("Data selection", href="/"),
                " page to choose a map to load based on sample metadata or original geographic location of the rock sample from which the x-ray map was derived.",
            ]
        ),
        _screenshot("data_selection", alt="The data selection page"),
        html.P(
            [
                "When the app runs in desktop mode, a ",
                html.B("Working directory"),
                " picker appears above the sample dropdown. Browse with its "
                "dropdown and ",
                html.B("Up"),
                ", optionally ",
                html.B("Include subdirectories"),
                ", then click ",
                html.B("Use this directory"),
                " to scan it for datasets.",
            ]
        ),
        html.P(
            [
                "You don't have to go through the map: open the ",
                dcc.Link("Inspector", href="/inspector/none"),
                " directly from the sidebar and pick a sample from its ",
                html.B("Sample"),
                " dropdown.",
            ]
        ),
        html.Hr(),
        html.H2("Inspector"),
        html.P(
            "A sample opened in Spectrum only mode has no images, so the "
            "inspector shows just its spectrum and export panel."
        ),
        html.H3("Image Panel Tools"),
        html.P("The toolbox above the image panels acts on every panel at once."),
        _screenshot(
            "inspector_toolbox", alt="The sample selector and image panel toolbox"
        ),
        html.H3("Image panels"),
        html.P(
            "The inspector opens with three image panels, each showing one "
            "element map of the sample."
        ),
        _screenshot(
            "inspector_panels", alt="Two image panels sharing a polygon selection"
        ),
        html.P(
            [
                "In ",
                html.B("multi-channel"),
                " mode, one composite panel blends up to three element maps "
                "into a colour image, where overlapping elements mix their "
                "colours. For each channel pick an element, and under ",
                html.B("Channel details"),
                " its colour, energy range and stretch (the percentiles of the "
                "map shown as black and as full colour). Click ",
                html.B("Apply"),
                " to blend.",
            ]
        ),
        html.H3("Spectrum"),
        _screenshot("inspector_spectrum", alt="The spectrum plot with peak windows"),
        html.P([html.B("Plot tools"), " holds:"]),
        html.Ul(
            [
                html.Li(
                    [
                        html.B("Zoom"),
                        " and ",
                        html.B("Pan"),
                        " as for the images. The zoom in / out buttons halve or "
                        "double the energy range about its centre, leaving the "
                        "intensity axis alone, and ",
                        html.B("Reset Extent"),
                        " returns to the full spectrum.",
                    ]
                ),
                html.Li([html.B("peak windows"), " shows or hides the peak windows."]),
                html.Li(
                    [
                        html.B("y scale"),
                        " switches the intensity axis between linear and log.",
                    ]
                ),
            ]
        ),
        html.H3("Element weights and export"),
        html.P(
            "The panel at the bottom of the inspector summarises the current spectrum."
        ),
        _screenshot(
            "inspector_export", alt="The export panel and element weights table"
        ),
        html.P(
            [
                "Once a region is selected, ",
                html.B("Figure settings"),
                " appears under Export summary. It controls whether the "
                "selection's outline is drawn on the exported images, and in "
                "which colours.",
            ]
        ),
    ]
)

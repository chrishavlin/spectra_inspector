from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import dash
import dash_bootstrap_components as dbc
import numpy as np
import numpy.typing as npt
import pandas as pd
import plotly.graph_objects as go
import requests
from dash import (
    ALL,
    ClientsideFunction,
    Input,
    Output,
    Patch,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    set_props,
)
from pydantic import BaseModel

from spectra_inspector.components import (
    bitmap_image_layout,
    bitmapImageLayoutIDs,
    data_export_panel,
    dataset_selector,
    datasetSelectorLayoutIDs,
    directory_selector,
    fetch_im_data_parallel,
    get_new_im,
    image_toolbox_layout,
)
from spectra_inspector.components.bitmap_image import colorscale_patch, graph_style
from spectra_inspector.components.composite_image import (
    channel_selector_ids,
    channel_specs_from_states,
    composite_figure,
    composite_image_layout,
    compositeChannelLayoutIDs,
    compositeImageLayoutIDs,
    get_composite_im,
)
from spectra_inspector.components.dataset_selector import (
    dataset_names,
    dropdown_options,
    list_store_data,
    resolve_spectrum_only,
)
from spectra_inspector.components.energy_range_slider import (
    APPLY_IDLE_PROPS,
    APPLY_PENDING_PROPS,
    elementDropdownSliderIDS,
)
from spectra_inspector.components.image_toolbox import (
    ADD_IMAGE,
    DRAW_POLYGON,
    IMAGE_TOOLBOX,
    POLYGON_CONTROLS_ID,
    POLYGON_NOTE_ID,
    SCALEBAR_COLOR_ID,
    SCALEBAR_FONTSIZE_ID,
    SCALEBAR_SHOW_ID,
    SUBMIT_SHAPE,
)
from spectra_inspector.components.scalebar import apply_style_to_patch, scalebarHandler
from spectra_inspector.components.spectrum_toolbox import (
    SPECTRUM_TOOLBOX,
    spectrum_toolbox_layout,
)
from spectra_inspector.components.toolbox import RESET_EXTENT, ZOOM_FACTORS
from spectra_inspector.logging import spectraLogger
from spectra_inspector.user_store_model import (
    USER_STORE_DIV_ID,
    UserStore,
    sample_metadata_for_store,
    updateDataStore,
)
from spectra_inspector.utilities.coerce import (
    placeholder_to_spaces,
    plotly_im_trace_to_array,
    plotly_image_trace_to_array,
    plotly_to_matplotlib,
)
from spectra_inspector.utilities.composite import compositeChannel
from spectra_inspector.utilities.export_metadata import (
    build_export_metadata,
    composite_image_metadata,
    single_image_metadata,
)
from spectra_inspector.utilities.interface import (
    ServerRequestError,
    SpectraInspectorServerInterface,
)
from spectra_inspector.utilities.peak_windows import (
    RANGES_KEY,
    apply_peak_windows,
    peak_windows,
)
from spectra_inspector.utilities.scalebar_style import (
    scalebar_style,
    scalebar_style_from_store,
    scalebar_styled,
    scalebarStyle,
)
from spectra_inspector.utilities.scaling import get_image_shape
from spectra_inspector.utilities.selection import (
    Selection,
    active_shapes,
    add_point,
    box_misses_image,
    boxSelection,
    insert_point_on_nearest_segment,
    move_point,
    outlineStyle,
    overlay_shapes,
    pick_tolerance,
    polygon_is_submittable,
    polygon_points,
    polygon_store,
    polygonSelection,
    remove_nearest_point,
    selection_from_store,
    selection_key,
    submitted_polygon,
    vertex_radius,
    vertex_radius_for,
)
from spectra_inspector.utilities.summary_writer import summaryWriter
from spectra_inspector.utilities.view_sync import (
    apply_axes_to_patch,
    apply_tool_to_patch,
    empty_view,
    ensure_view,
    image_axis_range,
    shapes_from_relayout,
    sorted_axis_range,
    update_view_from_relayout,
    zoom_view,
)

if TYPE_CHECKING:
    from spectra_inspector.utilities.model import AvailableDatasets, CombinedMetadata

dash.register_page(__name__, order=1, path_template="/inspector/<sample_name>")

NUMBER_OF_INITIAL_FIGURES = 3

scalebar_handler = scalebarHandler()


def _scalebar(scalebar_store: dict | None) -> scalebarHandler:
    """The scalebar handler drawing as the toolbox's scalebar store says."""
    return scalebar_handler.styled(scalebar_style_from_store(scalebar_store))


secondDatasetSelector = datasetSelectorLayoutIDs(index=1)


def _valid_sample_name(sample_name: str | None):
    return (
        sample_name is not None
        and sample_name != "none"
        and isinstance(sample_name, str)
    )


def _ensure_dataset(user_store_dict: dict, sample_name: str | None) -> dict:
    """Put the page's sample into a user store that names no dataset yet.

    On a fresh load the figure callbacks can run before
    ``update_selected_dataset`` has written the store, which then still holds
    the ``UserStore`` default of ``"none"``; the metadata is fetched from the
    server in that case.
    """
    if not _valid_sample_name(user_store_dict.get("selected_dataset")):
        user_store_dict["selected_dataset"] = sample_name
    return user_store_dict


def get_spectrum(
    sample_name: str,
    channel_range: tuple[int, int] | None = None,
    index0_range: tuple[int, int] | None = None,
    index1_range: tuple[int, int] | None = None,
    directory_sync: dict | None = None,
    spectrum_only: bool = False,
    polygon: list[list[float]] | None = None,
) -> pd.DataFrame:

    sisi = SpectraInspectorServerInterface()
    spectrum = sisi.get_image_spectrum(
        sample_name,
        channel_range=channel_range,
        index0_range=index0_range,
        index1_range=index1_range,
        directory_sync=directory_sync,
        spectrum_only=spectrum_only,
        polygon=polygon,
    )

    min_e = spectrum.energy_min
    max_e = spectrum.energy_max
    sz = len(spectrum.energy)
    e_diff = max_e - min_e
    spectraLogger.info(f"fetched spectrum with size {sz}, {min_e=}, {max_e=}")
    dx = e_diff / sz
    energy_scaled = np.arange(sz) * dx + min_e
    df = pd.DataFrame({"intensity": spectrum.intensity, "energy": energy_scaled})
    attrs = {
        "energy_max": spectrum.energy_max,
        "energy_min": spectrum.energy_min,
    }
    if spectrum.metadata is not None:
        attrs["metadata"] = spectrum.metadata
    if spectrum.original_metadata is not None:
        attrs["original_metadata"] = spectrum.original_metadata
    if spectrum.weights is not None:
        attrs["weights"] = spectrum.weights
    if spectrum.integration_ranges_keV is not None:
        attrs[RANGES_KEY] = {
            el: list(rng) for el, rng in spectrum.integration_ranges_keV.items()
        }
    df.attrs = attrs
    return df


def selected_sample_contents(sample_name: str | None) -> str:
    if _valid_sample_name(sample_name):
        assert isinstance(sample_name, str)
        valid_sample = placeholder_to_spaces(sample_name)
        msg = f"{valid_sample}"
    else:
        msg = "none"
    return msg


class inspectorIDs(BaseModel):
    metadata: str = "metadata-info"
    sample_name: str = "sample-name"
    image_container: str = "image-container"
    # the wrapper hidden in spectrum-only mode: the toolbox and the panels
    image_section: str = "image-section"
    spectrum_container: str = "spectrum-container"
    spectrum_yaxis_scale: str = "spectrum-yaxis-scale"
    spectrum_peak_windows: str = "spectrum-peak-windows"
    # the spectrum toolbox's tool, and where its clientside actions report
    spectrum_view_store: str = "spectrum-view"
    spectrum_action_sink: str = "spectrum-action-sink"
    image_mode: str = "image-mode"
    image_container_type: str = "bitmap-image"
    shapes_store: str = "active-shapes"
    # where the click listener in assets/toolbox.js reports polygon clicks
    polygon_click_store: str = "polygon-click"
    view_store: str = "image-view-store"
    # how the panels and the export draw the scalebar (the toolbox's controls)
    scalebar_style_store: str = "scalebar-style"
    processed_graph_id_store: str = "processed-graph-ids"
    graph_id_store: str = "graph-id-store"
    full_spectrum_store: str = "full-spectrum-store"
    active_spectrum_metadata: str = "active-spectrum-metadata"
    zeroed_elements_store: str = "zeroed-elements"


_IDS = inspectorIDs()
_imageIDS = bitmapImageLayoutIDs()
_imageSliderIds = elementDropdownSliderIDS()
_toolboxIDS = IMAGE_TOOLBOX.ids
_ADD_IMAGE_ID = _toolboxIDS.button_id(ADD_IMAGE.id)
_RESET_IMAGES_ID = _toolboxIDS.button_id(RESET_EXTENT.id)
_SUBMIT_SHAPE_ID = _toolboxIDS.button_id(SUBMIT_SHAPE.id)
_spectrumToolboxIDS = SPECTRUM_TOOLBOX.ids
_SPECTRUM_RESET_ID = _spectrumToolboxIDS.button_id(RESET_EXTENT.id)
_compositeIDS = compositeImageLayoutIDs()
_channelIDS = compositeChannelLayoutIDs()
_dataExportIDS = data_export_panel.dataExportPanelIDS(index=0)

# the element preset each of the first image panels opens on; panels added
# past these start on the first one.
_INITIAL_PANEL_ELEMENTS = ("Mg", "Al", "Si")

# the two kinds of image panel: one element map per panel, or one panel
# blending up to three maps. Switching kinds replaces every panel.
IMAGE_MODE_SINGLE = "single"
IMAGE_MODE_MULTI = "multi"
IMAGE_MODES = (
    {"label": "single channel", "value": IMAGE_MODE_SINGLE},
    {"label": "multi-channel", "value": IMAGE_MODE_MULTI},
)


def _get_div_store() -> html.Div:
    return html.Div(
        [
            dcc.Store(
                id=_IDS.graph_id_store,  # div id tracking
                storage_type="memory",
                data={"initialized": False},
            ),
            dcc.Store(
                id=_IDS.processed_graph_id_store,  # figure data
                storage_type="memory",
                data={"initialized": False},
            ),
            dcc.Store(
                id=_IDS.shapes_store,
                storage_type="memory",
                data={},
            ),
            dcc.Store(id=_IDS.polygon_click_store, storage_type="memory"),
            dcc.Store(
                id=_IDS.view_store,  # zoom + tool shared by the image panels
                storage_type="memory",
                data=empty_view(),
            ),
            dcc.Store(
                id=_IDS.scalebar_style_store,
                storage_type="memory",
                data=scalebarStyle().to_store(),
            ),
            dcc.Store(
                id=_IDS.spectrum_view_store,
                storage_type="memory",
                data={"dragmode": None},
            ),
            dcc.Store(id=_IDS.spectrum_action_sink, storage_type="memory"),
            dcc.Store(id=_IDS.full_spectrum_store, storage_type="memory", data={}),
            dcc.Store(id=_IDS.active_spectrum_metadata, storage_type="memory", data={}),
            # elements the user has zeroed out in the weights table; specific
            # to the active spectrum, so cleared whenever that changes
            dcc.Store(id=_IDS.zeroed_elements_store, storage_type="memory", data=[]),
        ]
    )


selectorIDs = datasetSelectorLayoutIDs(index=1)

SPECTRUM_YAXIS_SCALES = ("linear", "log")


def new_spectrum_figure(
    energy: list[float],
    intensity: list[float],
    yaxis_scale: str = "linear",
    active_spectrum_metadata: dict | None = None,
    show_peak_windows: bool | None = True,
    zeroed_elements: list[str] | None = None,
    dragmode: str | None = None,
    uirevision: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=energy, y=intensity, mode="lines", name="Full energy range")
    )
    # no vertical grid: the peaks' dotted centre lines are the only verticals
    fig.update_xaxes(
        title_text="Energy (keV)", autorangeoptions_maxallowed=8, showgrid=False
    )
    fig.update_yaxes(title_text="Intensity", type=_yaxis_type(yaxis_scale))
    windows = peak_windows(
        active_spectrum_metadata, show_peak_windows, zeroed_elements or []
    )
    fig.add_traces([go.Scatter(**trace) for trace in windows.traces])
    fig.update_layout(
        shapes=windows.shapes,
        annotations=windows.annotations,
        showlegend=False,
        dragmode=dragmode or SPECTRUM_TOOLBOX.default_tool,
        uirevision=uirevision,
    )
    return fig


def _spectrum_revision(sample_name: str | None, shapes_store: dict | None) -> str:
    """The spectrum figure's ``uirevision``: what the plot is showing.

    The figure prop never receives a zoom, so without a revision every patch
    (a tool pick, the peaks redrawn) would snap the plot back to autorange.
    With one, plotly keeps the browser's zoom as long as the revision is
    unchanged; it changes with the spectrum shown, so a new box, a submitted
    polygon or a new dataset does start from the full view.
    """
    return f"{sample_name}|{selection_key(shapes_store)}"


def _with_spectrum_dragmode(figure: dict, spectrum_view: dict | None) -> dict:
    """A figure dict about to replace the spectrum, carrying the toolbox's tool
    so the pressed button stays right."""
    figure.setdefault("layout", {})["dragmode"] = SPECTRUM_TOOLBOX.active_tool(
        spectrum_view
    )
    return figure


def _yaxis_type(yaxis_scale: str | None) -> str:
    return yaxis_scale if yaxis_scale in SPECTRUM_YAXIS_SCALES else "linear"


def _query_flag(value: str | bool | None) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def layout(
    sample_name: str | None = None,
    spectrum_only: str | None = None,
    **kwargs,  # noqa: ARG001
):
    """``spectrum_only`` arrives as the ``?spectrum_only=true`` query string
    the data selection page puts on its "Load Selected" link, which is the
    only way the mode can reach a layout -- the user store is client side."""

    spectrum_only_mode = _query_flag(spectrum_only)

    _layout_rows = []
    _layout_rows.append(html.Div(hidden=True, id=_IDS.metadata))

    sisi = SpectraInspectorServerInterface()
    _data_selector, _ = dataset_selector(
        sisi,
        component_index=1,
        sample_id=sample_name,
        dropdown_label="Sample: ",
        spectrum_only=spectrum_only_mode,
    )

    _layout_rows.append(directory_selector(component_index=1))

    image_control_card = dbc.Card(dbc.CardBody(_data_selector))

    _top_image_controls = dbc.Row(
        dbc.Col(
            [
                image_control_card,
                html.Div(
                    selected_sample_contents(sample_name),
                    id=_IDS.sample_name,
                    hidden=True,
                ),
            ],
            xs=12,
            lg=7,
            style={"maxWidth": "48rem"},
        )
    )

    _layout_rows.append(_top_image_controls)

    # a CSS grid rather than a bootstrap row: the breakpoints of dbc.Col are
    # keyed on the viewport, not on the content area beside the sidebar, so a
    # fixed column count leaves laptop-sized windows with panels too narrow to
    # read. auto-fit sizes the columns by the container itself and stretches
    # the panels present across its full width.
    im_container = dcc.Loading(
        html.Div(
            [],
            id=_IDS.image_container,
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(420px, 1fr))",
                "gap": "0.5rem",
            },
        ),
        id="full-im-container-loading",
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        type="circle",
    )
    # the toolbox sits with the panels so spectrum-only mode hides both
    mode_switch = dbc.RadioItems(
        id=_IDS.image_mode,
        options=list(IMAGE_MODES),
        value=IMAGE_MODE_SINGLE,
        className="btn-group btn-group-sm",
        inputClassName="btn-check",
        labelClassName="btn btn-outline-secondary text-nowrap",
        labelCheckedClassName="active",
    )
    toolbox_card, _ = image_toolbox_layout([mode_switch])
    _layout_rows.append(
        html.Div(
            [toolbox_card, im_container],
            id=_IDS.image_section,
            hidden=spectrum_only_mode,
        )
    )

    spectrum_graph = dcc.Loading(
        dcc.Graph(
            id=_IDS.spectrum_container,
            config={"displayModeBar": False, "scrollZoom": True},
        ),
        id="spectrum-loading",
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        type="circle",
    )

    # the display switches fill the toolbox's second row
    spectrum_controls = [
        dbc.Switch(
            id=_IDS.spectrum_peak_windows,
            label="peak windows",
            value=True,
            className="mb-0 me-3",
            label_class_name="mb-0",
        ),
        html.Label("y scale:", className="mb-0 me-2"),
        dbc.RadioItems(
            options=[{"label": s, "value": s} for s in SPECTRUM_YAXIS_SCALES],
            value="linear",
            id=_IDS.spectrum_yaxis_scale,
            inline=True,
            className="d-flex align-items-center",
            inputCheckedClassName="",
            labelCheckedClassName="",
        ),
    ]
    tools_toggle, tools_collapse, _ = spectrum_toolbox_layout(spectrum_controls)

    spectrum_div = dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(dbc.Col(spectrum_graph, width=12), className="gx-1 gy-1"),
                html.Div(tools_toggle, className="d-flex justify-content-end mb-2"),
                tools_collapse,
            ]
        ),
        # color="primary",
        style={"margin-top": "1rem"},
    )

    _layout_rows.append(_get_div_store())
    _layout_rows.append(spectrum_div)

    export_panel = dbc.Row(
        [
            dbc.Col(data_export_panel.get_layout()[0], width=12),
        ],
        style={"margin-top": "1rem"},
    )
    _layout_rows.append(export_panel)
    return dbc.Container(_layout_rows, fluid=True)


@callback(
    Output(_IDS.full_spectrum_store, "data", allow_duplicate=True),
    Input(_IDS.sample_name, "children"),
    Input(_IDS.full_spectrum_store, "data"),
    State(USER_STORE_DIV_ID, "data"),
    running=[
        (Output("spectrum-loading", "display"), "show", "hide"),
        (Output(_ADD_IMAGE_ID, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def initialize_full_spectrum_data(
    sample_name: str | None,
    spectrum_store: dict | None,
    user_store_dict: dict | None,
):

    has_data = isinstance(spectrum_store, dict) and "intensity" in spectrum_store

    if _valid_sample_name(sample_name) and not has_data:
        spectraLogger.info("fetching and storing full spectrum data")
        assert isinstance(sample_name, str)
        user_store = UserStore(**(user_store_dict or {}))
        df = get_spectrum(
            sample_name,
            directory_sync=user_store.directory_sync(),
            spectrum_only=user_store.spectrum_only,
        )
        new_store_data = {}
        new_store_data["intensity"] = df.intensity.tolist()
        new_store_data["energy"] = df.energy.tolist()
        new_store_data["attrs"] = df.attrs
        return new_store_data

    return no_update


@callback(
    Output(_dataExportIDS.elementweightsdiv, "children"),
    Input(_IDS.active_spectrum_metadata, "data"),
    Input(_IDS.zeroed_elements_store, "data"),
)
def update_element_weights(
    active_spectrum_metadata: dict | None,
    zeroed_elements: list[str] | None,
):
    if active_spectrum_metadata and "attrs" in active_spectrum_metadata:
        tble = data_export_panel.get_formatted_element_weights(
            active_spectrum_metadata,
            zeroed_elements=zeroed_elements or [],
            ids=_dataExportIDS,
        )
        return html.Div(tble)
    return html.Div()


@callback(
    Output(_IDS.zeroed_elements_store, "data", allow_duplicate=True),
    Input(_IDS.active_spectrum_metadata, "data"),
    prevent_initial_call=True,
)
def clear_zeroed_elements(_active_spectrum_metadata):
    # a new spectrum (dataset switch, new box) gets a fresh weights table
    return []


@callback(
    Output(_IDS.zeroed_elements_store, "data", allow_duplicate=True),
    Input({"type": _dataExportIDS.zeroelement, "index": ALL}, "n_clicks"),
    Input(_dataExportIDS.resetweights, "n_clicks"),
    State(_IDS.zeroed_elements_store, "data"),
    prevent_initial_call=True,
)
def update_zeroed_elements(_zero_clicks, _reset_clicks, zeroed_elements):
    # re-rendering the weights table recreates the X buttons, which fires this
    # with every n_clicks back at zero; only a real click carries a count.
    if not any(trigger["value"] for trigger in ctx.triggered):
        return no_update

    trigger_id = ctx.triggered_id
    if trigger_id == _dataExportIDS.resetweights:
        return []

    # the row button toggles: X zeroes the element, the restore arrow un-zeroes it
    zeroed = list(zeroed_elements or [])
    element = trigger_id["index"]
    if element in zeroed:
        return [el for el in zeroed if el != element]
    return [*zeroed, element]


@callback(
    Output(_IDS.spectrum_container, "figure", allow_duplicate=True),
    Output(_IDS.active_spectrum_metadata, "data", allow_duplicate=True),
    Input(_IDS.shapes_store, "data"),
    Input(_IDS.full_spectrum_store, "data"),
    State(_IDS.sample_name, "children"),
    State(_IDS.spectrum_container, "figure"),
    State(_IDS.active_spectrum_metadata, "data"),
    State(USER_STORE_DIV_ID, "data"),
    State(_IDS.spectrum_yaxis_scale, "value"),
    State(_IDS.spectrum_peak_windows, "value"),
    State(_IDS.zeroed_elements_store, "data"),
    State(_IDS.spectrum_view_store, "data"),
    running=[
        (Output("spectrum-loading", "display"), "show", "hide"),
        (Output(_ADD_IMAGE_ID, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def update_spectrum(
    shapes_store: dict | None,
    full_spectrum_store: dict | None,
    sample_name: str | None,
    current_figure,
    active_spectrum_metadata: dict | None,
    user_store_dict: dict | None,
    yaxis_scale: str | None,
    show_peak_windows: bool | None,
    zeroed_elements: list[str] | None,
    spectrum_view: dict | None,
):

    spectraLogger.info(f"update_spectrum trigger: {ctx.triggered_id}")

    if full_spectrum_store is None or "intensity" not in full_spectrum_store:
        # full spectrum data not fetched yet, return
        return no_update, no_update

    if current_figure is None:
        # now we have data but no figure, create it
        active_spectrum_metadata = full_spectrum_store.copy()
        current_figure = new_spectrum_figure(
            full_spectrum_store["energy"],
            full_spectrum_store["intensity"],
            yaxis_scale,
            active_spectrum_metadata,
            show_peak_windows,
            zeroed_elements,
            dragmode=SPECTRUM_TOOLBOX.active_tool(spectrum_view),
            uirevision=_spectrum_revision(sample_name, shapes_store),
        )

        return current_figure, active_spectrum_metadata

    # finally, we have a figure, but only update if the selection has changed:
    # the shapes store also moves while a polygon is being placed, which does
    # not change what the spectrum sums over until the shape is submitted
    revision = _spectrum_revision(sample_name, shapes_store)
    if (current_figure.get("layout") or {}).get("uirevision") == revision:
        return no_update, no_update

    if shapes_store is not None:
        selection = _selection_for_request(shapes_store, user_store_dict, sample_name)
        name = "full spectrum"

        if active_spectrum_metadata is None:
            active_spectrum_metadata = {}

        if selection is not None:
            assert isinstance(sample_name, str)
            request_kwargs = selection.request_kwargs()
            spectraLogger.info(f"fetching subsample spectrum with {request_kwargs}")
            user_store = UserStore(**(user_store_dict or {}))
            df = get_spectrum(
                sample_name,
                directory_sync=user_store.directory_sync(),
                spectrum_only=user_store.spectrum_only,
                **request_kwargs,
            )
            name = "spatial subset"
            active_spectrum_metadata["intensity"] = df.intensity.tolist()
            active_spectrum_metadata["energy"] = df.energy.tolist()
            active_spectrum_metadata["attrs"] = df.attrs
        else:
            # just re-load the full spectum
            df = full_spectrum_store
            active_spectrum_metadata = full_spectrum_store.copy()

        new_trace = {
            "mode": "lines",
            "x": df["energy"],
            "y": df["intensity"],
            "type": "scatter",
            "name": name,
        }

        current_figure["data"][0] = new_trace
        current_figure["layout"]["uirevision"] = revision
        # the peaks follow the new curve, and a spatial subset may have lost
        # its calibration (and so its windows) altogether
        current_figure = apply_peak_windows(
            current_figure,
            active_spectrum_metadata,
            show_peak_windows,
            zeroed_elements or [],
        )
        return (
            _with_spectrum_dragmode(current_figure, spectrum_view),
            active_spectrum_metadata,
        )

    return no_update, no_update


@callback(
    Output(_IDS.spectrum_container, "figure", allow_duplicate=True),
    Input(_IDS.spectrum_yaxis_scale, "value"),
    State(_IDS.spectrum_container, "figure"),
    prevent_initial_call=True,
)
def set_spectrum_yaxis_scale(yaxis_scale: str | None, current_figure):
    if current_figure is None:
        # nothing drawn yet; the figure picks the scale up when it is created
        return no_update
    patched = Patch()
    patched["layout"]["yaxis"]["type"] = _yaxis_type(yaxis_scale)
    # a range zoomed on the old scale means nothing on the new one: bumping
    # the axis's own revision lets it autorange while the energy zoom stays
    patched["layout"]["yaxis"]["uirevision"] = _yaxis_type(yaxis_scale)
    return patched


@callback(
    Output(_IDS.spectrum_container, "figure", allow_duplicate=True),
    Input(_IDS.spectrum_peak_windows, "value"),
    Input(_IDS.zeroed_elements_store, "data"),
    State(_IDS.spectrum_container, "figure"),
    State(_IDS.active_spectrum_metadata, "data"),
    State(_IDS.spectrum_view_store, "data"),
    prevent_initial_call=True,
)
def toggle_peak_windows(
    show_peak_windows: bool | None,
    zeroed_elements: list[str] | None,
    current_figure,
    active_spectrum_metadata: dict | None,
    spectrum_view: dict | None,
):
    """Redraw the peaks when the switch flips or an element is zeroed out or
    restored in the weights table; the spectrum itself is not refetched."""
    if current_figure is None or not current_figure.get("data"):
        return no_update
    redrawn = apply_peak_windows(
        current_figure,
        active_spectrum_metadata,
        show_peak_windows,
        zeroed_elements or [],
    )
    assert redrawn is not None
    return _with_spectrum_dragmode(redrawn, spectrum_view)


@callback(
    Output(_ADD_IMAGE_ID, "n_clicks"),
    Input(_IDS.sample_name, "children"),
    State(USER_STORE_DIV_ID, "data"),
    State(selectorIDs.get_id_with_index("spectrumonly"), "value"),
)
def initial_update(
    input_value: str | None,
    user_store_dict: dict | None,
    spectrum_only_switch: bool | None = False,
):
    """Open the initial image panels for a newly selected map.

    A spectrum has no images, so nothing is opened for it. The mode comes off
    the user store, or off the switch as the page rendered it when this fires
    on a fresh load before the store has been written.
    """
    if resolve_spectrum_only(user_store_dict, spectrum_only_switch):
        return no_update
    if _valid_sample_name(input_value):
        return NUMBER_OF_INITIAL_FIGURES
    return no_update


def _find_id_in_list(
    type: str, index: int, el_list: list[dict[str, str | int]]
) -> None | int:
    id_to_find = {"index": index, "type": type}
    if id_to_find in el_list:
        return el_list.index(id_to_find)
    id_to_find2 = {"type": type, "index": index}
    if id_to_find2 in el_list:
        return el_list.index(id_to_find2)
    return None


def _image_shape_or_none(md: "CombinedMetadata | None") -> tuple[int, int] | None:
    return get_image_shape(md) if md is not None else None


def _selection_for_request(
    shapes_store: dict | None, user_store_dict: dict | None, sample_name: str | None
) -> Selection | None:
    """The store's selection as the server takes it: a box is clipped to the
    map (the server rejects index ranges past it), which needs the metadata;
    a polygon and no selection need nothing."""
    selection = selection_from_store(shapes_store)
    if not isinstance(selection, boxSelection):
        return selection
    user_store_dict = user_store_dict or {}
    _ensure_dataset(user_store_dict, sample_name)
    md = UserStore(**user_store_dict).conditionally_fetch_metadata()
    return selection_from_store(shapes_store, _image_shape_or_none(md))


def _shapes_after_relayout(
    relay: dict, shapes_store: dict | None, fetch_metadata: Callable[[], Any]
) -> tuple[list[dict], bool, bool]:
    """``(shapes, redraw, keep)``: the shapes a relayout event leaves on the
    panels, whether they differ from what the panels show, and whether they
    are the selection to store. A box dragged wholly off the map is no
    selection: the panels are put back to the stored shapes and the store is
    left alone, so nothing is synced, shown or requested for it."""
    current = _active_shapes(shapes_store)
    shapes, changed = shapes_from_relayout(relay, current)
    if not changed:
        return shapes, False, False
    if shapes and shapes[0].get("type") == "rect":
        md = fetch_metadata()
        if md is not None and box_misses_image(shapes, get_image_shape(md)):
            return current, True, False
    return shapes, True, True


def _selection_bounds(
    selection: Selection | None, md: "CombinedMetadata | None"
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """The index ranges the exported ``*_subset`` images are cropped to: the
    box itself, or the pixel rectangle around the polygon clipped to the map."""
    if selection is None:
        return None
    image_shape = get_image_shape(md) if md is not None else None
    return selection.bounding_box(image_shape)


def _new_panel(mode: str | None, index: int) -> tuple[dbc.Card, dict[str, str | int]]:
    """A panel card of the current kind and its div id."""
    if mode == IMAGE_MODE_MULTI:
        card, imIDs = composite_image_layout(
            index, id_type_base=_IDS.image_container_type
        )
    else:
        if index < len(_INITIAL_PANEL_ELEMENTS):
            init_element = _INITIAL_PANEL_ELEMENTS[index]
        else:
            init_element = _INITIAL_PANEL_ELEMENTS[0]
        card, imIDs = bitmap_image_layout(
            index,
            id_type_base=_IDS.image_container_type,
            init_element=init_element,
        )
    return card, imIDs.get_id_with_index("div")


def _initial_panel_count(mode: str | None, n_clicks: int) -> int:
    """How many panels a fresh page opens with: the usual three element maps,
    or a single composite."""
    return 1 if mode == IMAGE_MODE_MULTI else n_clicks


@callback(
    Output(_IDS.image_container, "children", allow_duplicate=True),
    Output(_IDS.graph_id_store, "data", allow_duplicate=True),
    Input(_ADD_IMAGE_ID, "n_clicks"),
    Input({"type": _imageIDS.delete, "index": ALL}, "n_clicks"),
    State(_IDS.graph_id_store, "data"),
    State(_IDS.image_mode, "value"),
    running=[
        (Output(_ADD_IMAGE_ID, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def add_or_delete_image(
    n_clicks: int | None,
    n_clicks_delete: list[int | None],
    graph_id_store: dict,
    image_mode: str | None,
):
    """Append a panel card or drop one, as a patch on the container's children.

    The container is never read back: its children carry every panel's figure,
    image data included, and a State is uploaded with the request whichever
    button fired. The position of the card to drop comes from the id store,
    which also hands out panel indices (``next_index``) so a panel never
    reuses the index of one that was removed or replaced.
    """
    button_clicked = ctx.triggered_id
    spectraLogger.info(f"add_or_delete_image button: {button_clicked}")
    n_deletes = sum([n for n in n_clicks_delete if n is not None])

    if "active_div_ids" not in graph_id_store:
        graph_id_store["active_div_ids"] = []

    if button_clicked == _ADD_IMAGE_ID and n_clicks is not None:
        patched_children = Patch()

        if graph_id_store["initialized"] is False:
            n_new = _initial_panel_count(image_mode, n_clicks)
            graph_id_store["initialized"] = True
        else:
            n_new = 1

        start = graph_id_store.get("next_index", 0)
        for id_index in range(start, start + n_new):
            new_image_div, new_div_id = _new_panel(image_mode, id_index)
            patched_children.append(new_image_div)
            graph_id_store["active_div_ids"].append(new_div_id)
        graph_id_store["next_index"] = start + n_new
        return patched_children, graph_id_store
    if button_clicked is not None and n_deletes > 0:
        pop_id = _find_id_in_list(
            _imageIDS.div, button_clicked["index"], graph_id_store["active_div_ids"]
        )
        if pop_id is None:
            return no_update, graph_id_store
        patched_children = Patch()
        del patched_children[pop_id]
        graph_id_store["active_div_ids"].pop(pop_id)
        return patched_children, graph_id_store

    return no_update, graph_id_store


@callback(
    Output(_IDS.image_container, "children", allow_duplicate=True),
    Output(_IDS.graph_id_store, "data", allow_duplicate=True),
    Output(_IDS.processed_graph_id_store, "data", allow_duplicate=True),
    Input(_IDS.image_mode, "value"),
    State(_IDS.sample_name, "children"),
    State(USER_STORE_DIV_ID, "data"),
    State(selectorIDs.get_id_with_index("spectrumonly"), "value"),
    running=[
        (Output(_ADD_IMAGE_ID, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def switch_image_mode(
    image_mode: str | None,
    sample_name: str | None,
    user_store_dict: dict | None,
    spectrum_only_switch: bool | None = False,
):
    """Replace every panel with the other kind: three element maps, or one
    composite. The panels are rebuilt from scratch, so the processed-id store
    is emptied and the figure callbacks fetch the new panels' images (into the
    shared view and box, which are kept)."""
    if resolve_spectrum_only(user_store_dict, spectrum_only_switch):
        return no_update, no_update, no_update
    if not _valid_sample_name(sample_name):
        return no_update, no_update, no_update

    n_new = _initial_panel_count(image_mode, NUMBER_OF_INITIAL_FIGURES)
    children = []
    active_div_ids = []
    for index in range(n_new):
        card, div_id = _new_panel(image_mode, index)
        children.append(card)
        active_div_ids.append(div_id)
    graph_id_store = {
        "initialized": True,
        "active_div_ids": active_div_ids,
        "next_index": n_new,
    }
    return children, graph_id_store, {"initialized": False}


@callback(
    Output(_dataExportIDS.downloadmsa, "data"),
    Input(_dataExportIDS.exportmsa, "n_clicks"),
    State(_IDS.active_spectrum_metadata, "data"),
    State(_dataExportIDS.msafileformat, "value"),
    State(_dataExportIDS.msafiletype, "value"),
    running=[
        (Output(_dataExportIDS.exportsummary, "disabled"), True, False),
        (Output(_dataExportIDS.exportmsa, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def export_msa(
    export_clicks: int | None,
    active_spectrum_metadata,
    msafileformat: Literal["Y", "XY"] | None,
    msafiletype: Literal[".msa", ".csv"] | None,
):
    if export_clicks is None:
        return None

    s = summaryWriter()
    f = s.write_MSA(
        active_spectrum_metadata, file_format=msafileformat, file_type=msafiletype
    )
    return dcc.send_file(f)


@callback(
    Output(_dataExportIDS.downloadsummary, "data"),
    Input(_dataExportIDS.exportsummary, "n_clicks"),
    State({"type": _imageIDS.graph, "index": ALL}, "figure"),
    State(_IDS.shapes_store, "data"),
    State("sample-name", "children"),
    State({"type": _imageSliderIds.slider, "index": ALL}, "value"),
    State({"type": _imageSliderIds.dropdown, "index": ALL}, "value"),
    State(_IDS.spectrum_container, "figure"),
    State({"type": _imageIDS.colorscale, "index": ALL}, "value"),
    State(USER_STORE_DIV_ID, "data"),
    State(_dataExportIDS.formatdropdown, "value"),
    State(_IDS.active_spectrum_metadata, "data"),
    State(_dataExportIDS.msafileformat, "value"),
    State(_IDS.zeroed_elements_store, "data"),
    State(_IDS.spectrum_yaxis_scale, "value"),
    State(_IDS.spectrum_peak_windows, "value"),
    State(selectorIDs.get_id_with_index("spectrumonly"), "value"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State({"type": _imageSliderIds.slider, "index": ALL}, "id"),
    State({"type": _compositeIDS.apply, "index": ALL}, "id"),
    State({"type": channel_selector_ids.dropdown, "index": ALL}, "value"),
    State({"type": channel_selector_ids.dropdown, "index": ALL}, "id"),
    State({"type": channel_selector_ids.slider, "index": ALL}, "value"),
    State({"type": channel_selector_ids.slider, "index": ALL}, "id"),
    State({"type": _channelIDS.color, "index": ALL}, "value"),
    State({"type": _channelIDS.color, "index": ALL}, "id"),
    State({"type": _channelIDS.stretch, "index": ALL}, "value"),
    State({"type": _channelIDS.stretch, "index": ALL}, "id"),
    State(_dataExportIDS.includeoutline, "value"),
    State(_dataExportIDS.outlinelinecolor, "value"),
    State(_dataExportIDS.outlinedotcolor, "value"),
    State(_IDS.scalebar_style_store, "data"),
    prevent_initial_call=True,
    running=[
        (Output(_dataExportIDS.exportsummary, "disabled"), True, False),
        (Output(_dataExportIDS.exportmsa, "disabled"), True, False),
    ],
)
def export_summary(
    export_clicks: int | None,
    fig_list,
    shapes_store,
    sample_name,
    slider_range_list,
    slider_range_labels,
    spectrum_figure,
    colormaps,
    user_store_dict,
    export_summary_format: Literal[".zip", "PDF"] | None,
    active_spectrum_metadata: dict | None,
    msafileformat: Literal["Y", "XY"] | None,
    zeroed_elements: list[str] | None,
    spectrum_yaxis_scale: str | None,
    show_peak_windows: bool | None = True,
    spectrum_only_switch: bool | None = False,
    graph_ids: list[dict] | None = None,
    slider_ids: list[dict] | None = None,
    composite_apply_ids: list[dict] | None = None,
    channel_elements: list | None = None,
    channel_element_ids: list[dict] | None = None,
    channel_ranges: list | None = None,
    channel_range_ids: list[dict] | None = None,
    channel_colors: list | None = None,
    channel_color_ids: list[dict] | None = None,
    channel_stretches: list | None = None,
    channel_stretch_ids: list[dict] | None = None,
    include_outline: bool | None = None,
    outline_line_color: str | None = None,
    outline_dot_color: str | None = None,
    scalebar_store: dict | None = None,
):
    """Write the summary export: the spectrum plus, for a map, every image
    panel (and its box subset). A spectrum-only dataset has no images, so the
    panels are not consulted at all in that mode, whatever the page holds.

    The spectrum carries its peaks into the export exactly as the page shows
    them: the "peak windows" switch and the zeroed-out elements both apply.
    The images draw the scalebar and the selection as the figure export
    settings say."""

    if export_clicks is None or export_clicks == 0:
        return None

    _ensure_dataset(user_store_dict, sample_name)
    user_store = UserStore(**user_store_dict)
    spectrum_only = resolve_spectrum_only(user_store_dict, spectrum_only_switch)

    composite_specs: dict[int, list[compositeChannel]] = {}
    if composite_apply_ids:
        composite_specs = channel_specs_from_states(
            channel_elements or [],
            channel_element_ids or [],
            channel_ranges or [],
            channel_range_ids or [],
            channel_colors or [],
            channel_color_ids or [],
            channel_stretches or [],
            channel_stretch_ids or [],
        )
    panels = _panel_exports(
        fig_list,
        graph_ids,
        slider_range_list,
        slider_range_labels,
        colormaps,
        slider_ids,
        composite_specs,
    )

    figs_to_write = {}
    if not spectrum_only:
        style = data_export_panel.outline_style(
            include_outline, outline_line_color, outline_dot_color
        )
        scalebar = scalebar_style_from_store(scalebar_store)
        figs_to_write.update(
            _image_figures_to_write(user_store, panels, shapes_store, style, scalebar)
        )
    figs_to_write["spectrum"] = plotly_to_matplotlib(
        apply_peak_windows(
            spectrum_figure,
            active_spectrum_metadata,
            show_peak_windows,
            zeroed_elements or [],
        ),
        yaxis_scale=_yaxis_type(spectrum_yaxis_scale),
    )

    s = summaryWriter()
    s.write_static_figures(figs_to_write)
    s.set_export_metadata(
        _export_metadata(
            user_store,
            shapes_store,
            spectrum_only,
            panels,
            zeroed_elements,
            show_peak_windows,
        )
    )

    if export_summary_format == "PDF":
        return dcc.send_file(s.get_pdf_path(generate_pdf=True))
    if export_summary_format == ".zip" and active_spectrum_metadata is not None:
        # include the MSA for the zip as .msa and .csv
        _ = s.write_MSA(
            active_spectrum_metadata, file_type=".msa", file_format=msafileformat
        )
        _ = s.write_MSA(active_spectrum_metadata, file_type=".csv")
        wts = data_export_panel.get_element_weights(active_spectrum_metadata)
        if wts is None:
            # nothing to export: the weights file is simply left out of the zip
            spectraLogger.info("no element weights available, skipping their export")
        else:
            _ = s.write_element_weights(
                data_export_panel.apply_zeroed_elements(wts, zeroed_elements or [])
            )
        # last, so the README lists every other file in the zip
        _ = s.write_metadata_files()

        return dcc.send_file(s.get_zip())
    msg = f"Unexpected value for format, {export_summary_format=}"
    raise ValueError(msg)


@dataclass
class panelExport:
    """What the export needs to know about one image panel: the file stem it
    writes to, its figure and either the single map's settings or the
    composite's channels."""

    stem: str
    figure: dict
    energy_range: tuple[float, float] | None = None
    element_label: str | None = None
    colormap: str | None = None
    channels: list[compositeChannel] | None = None

    @property
    def composite(self) -> bool:
        return self.channels is not None

    def metadata(self, has_subset: bool) -> dict[str, Any]:
        if self.channels is not None:
            return composite_image_metadata(
                self.stem, [ch.metadata() for ch in self.channels], has_subset
            )
        assert self.energy_range is not None
        return single_image_metadata(
            self.stem,
            self.energy_range,
            self.element_label,
            self.colormap,
            has_subset,
        )


def _panel_exports(
    fig_list: list,
    graph_ids: list[dict] | None,
    slider_range_list: list,
    slider_range_labels: list,
    colormaps: list,
    slider_ids: list[dict] | None,
    composite_specs: dict[int, list[compositeChannel]],
) -> list[panelExport]:
    """One record per panel, in page order.

    A panel whose graph index has composite channels is a composite; any other
    is a single map whose slider, label and colormap are found by graph index
    when the ids are known, by position otherwise (the lists are then 1:1
    with the panels)."""
    slider_pos = {str(id_["index"]): pos for pos, id_ in enumerate(slider_ids or [])}
    panels = []
    for igraph, fig in enumerate(fig_list):
        stem = f"bitmap_{str(igraph).zfill(2)}"
        index = graph_ids[igraph]["index"] if graph_ids else None
        if index is not None and index in composite_specs:
            channels = composite_specs[index]
            stem += "_composite"
            elements = [
                ch.element for ch in channels if ch.active and ch.element == ch.label
            ]
            if elements:
                stem += "_" + "-".join(elements)
            panels.append(panelExport(stem, fig, channels=channels))
            continue

        pos = slider_pos.get(str(index), igraph) if index is not None else igraph
        label = slider_range_labels[pos]
        if label != "none":
            stem += f"_{label}"
        panels.append(
            panelExport(
                stem,
                fig,
                energy_range=tuple(slider_range_list[pos]),
                element_label=label,
                colormap=colormaps[pos],
            )
        )
    return panels


def _export_metadata(
    user_store: UserStore,
    shapes_store: dict | None,
    spectrum_only: bool,
    panels: list[panelExport],
    zeroed_elements: list[str] | None,
    show_peak_windows: bool | None,
) -> dict:
    """The record written next to the exported files: the sample
    metadata as the data-selection accordion shows it, the box in index and
    physical units, and what each image file holds.

    The metadata normally sits in the user store; a fresh session landing on
    the inspector URL has to fetch it, and that failing is logged rather than
    losing the export."""
    md: CombinedMetadata | None
    try:
        md = user_store.conditionally_fetch_metadata()
    except (requests.exceptions.RequestException, ServerRequestError):
        spectraLogger.exception("could not fetch the metadata for the export")
        md = None

    index_ranges = None
    polygon = None
    images = None
    if not spectrum_only:
        selection = selection_from_store(shapes_store, _image_shape_or_none(md))
        index_ranges = _selection_bounds(selection, md)
        if isinstance(selection, polygonSelection):
            polygon = selection.vertices
        images = [panel.metadata(index_ranges is not None) for panel in panels]

    return build_export_metadata(
        dataset=user_store.selected_dataset,
        md=md,
        sample_metadata=user_store.sample_metadata,
        spectrum_only=spectrum_only,
        index_ranges=index_ranges,
        polygon=polygon,
        images=images,
        zeroed_elements=zeroed_elements,
        show_peak_windows=show_peak_windows,
    )


def _with_shapes(figure: dict, shapes: list[dict]) -> dict:
    """The figure with ``shapes`` as its only layout shapes."""
    return {**figure, "layout": {**(figure.get("layout") or {}), "shapes": shapes}}


def _image_figures_to_write(
    user_store: UserStore,
    panels: list[panelExport],
    shapes_store: dict | None,
    style: outlineStyle | None = None,
    scalebar: scalebarStyle | None = None,
) -> dict:
    """Matplotlib versions of every image panel, plus the subset of each when
    a selection is drawn, keyed by output file stem. The subset is the box,
    or the pixel rectangle around the polygon. The selection is drawn on the
    images as ``style`` says (``overlay_shapes``), never as the browser
    happened to draw it, and the scalebar as ``scalebar`` says
    (``scalebar_styled``) rather than as the panels colour it."""
    style = style or outlineStyle()
    scalebar = scalebar or scalebarStyle()
    handler = scalebar_handler.styled(scalebar)

    def styled(figure: dict, shapes: list[dict]) -> dict:
        return scalebar_styled(_with_shapes(figure, shapes), scalebar)

    index0_range = None
    index1_range = None
    full_shapes: list[dict] = []
    subset_shapes: list[dict] = []
    md: CombinedMetadata | None = None
    selection = selection_from_store(shapes_store)
    if selection is not None:
        md = user_store.conditionally_fetch_metadata()
        assert md is not None
        image_shape = get_image_shape(md)
        selection = selection_from_store(shapes_store, image_shape)
        assert selection is not None
        bounds = selection.bounding_box(image_shape)
        index0_range, index1_range = bounds
        full_shapes = overlay_shapes(selection, style, image_shape)
        crop_shape = (
            index0_range[1] - index0_range[0],
            index1_range[1] - index1_range[0],
        )
        subset_shapes = overlay_shapes(selection, style, crop_shape, bounds)

    figs_to_write = {}
    for panel in panels:
        figs_to_write[panel.stem] = plotly_to_matplotlib(
            styled(panel.figure, full_shapes), cmap=panel.colormap
        )
        if not (index0_range and index1_range):
            continue

        subset_name = f"{panel.stem}_subset"
        if panel.composite:
            assert panel.channels is not None
            # the blend is already in the pixels: crop them and redraw
            rgb = plotly_image_trace_to_array(panel.figure["data"][0])
            rgb = rgb[
                index0_range[0] : index0_range[1],
                index1_range[0] : index1_range[1],
            ]
            if md is None:
                md = user_store.conditionally_fetch_metadata()
            assert md is not None
            newfig = composite_figure(
                rgb,
                panel.channels,
                md,
                scalebar_handler=handler,
                shapes=subset_shapes,
            )
            figs_to_write[subset_name] = plotly_to_matplotlib(
                scalebar_styled(newfig.to_plotly_json(), scalebar), im_data=rgb
            )
            continue

        im = plotly_im_trace_to_array(panel.figure["data"][0])
        zmin, zmax = np.min(im), np.max(im)
        im = im[
            index0_range[0] : index0_range[1],
            index1_range[0] : index1_range[1],
        ]
        assert panel.energy_range is not None
        newfig = get_new_im(
            user_store,
            panel.energy_range,
            panel.colormap,
            im,
            scalebar_handler=handler,
            zmin=zmin,
            zmax=zmax,
            shapes=subset_shapes,
        )
        figs_to_write[subset_name] = plotly_to_matplotlib(
            scalebar_styled(newfig.to_plotly_json(), scalebar),
            im_data=im,
            cmap=panel.colormap,
        )

    return figs_to_write


def _graph_dict(index: int) -> dict[str, str | int]:
    return {"type": _imageIDS.graph, "index": index}


def _apply_button_id(index: int) -> dict[str, str | int]:
    return {"type": _imageSliderIds.refreshbutton, "index": index}


def _composite_apply_id(index: int) -> dict[str, str | int]:
    return {"type": _compositeIDS.apply, "index": index}


def _active_shapes(shapes_store: dict | None) -> list[dict]:
    return active_shapes(shapes_store)


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure"),
    Output(_IDS.processed_graph_id_store, "data"),
    Output(_IDS.view_store, "data", allow_duplicate=True),
    Input({"type": _imageSliderIds.refreshbutton, "index": ALL}, "n_clicks"),
    Input(_RESET_IMAGES_ID, "n_clicks"),
    State({"type": _imageSliderIds.refreshbutton, "index": ALL}, "id"),
    State({"type": _imageIDS.colorscale, "index": ALL}, "value"),
    State(_IDS.graph_id_store, "data"),
    State({"type": _imageSliderIds.slider, "index": ALL}, "value"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(USER_STORE_DIV_ID, "data"),
    State(_IDS.processed_graph_id_store, "data"),
    State("sample-name", "children"),
    State({"type": _imageIDS.graph, "index": ALL}, "figure"),
    State(_IDS.view_store, "data"),
    State(_IDS.shapes_store, "data"),
    State(_IDS.scalebar_style_store, "data"),
    running=[
        (Output("full-im-container-loading", "display"), "show", "hide"),
        (Output(_ADD_IMAGE_ID, "disabled"), True, False),
        (Output(_RESET_IMAGES_ID, "disabled"), True, False),
        (Output(_dataExportIDS.exportsummary, "disabled"), True, False),
        (Output(_dataExportIDS.exportmsa, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def update_graph_figure(
    n_clicks: list[int | None],  # noqa: ARG001
    reset_nclicks: int | None,
    refresh_ids: list[dict[str, str | int]],
    colormap_choices: list[str | None],
    graph_id_store: dict,
    slider_range_list: list[tuple[float, float]],
    graph_ids: list[dict[str, str | int]],
    user_store_dict: dict,
    processed_graph_store: dict,
    sample_name: str,
    fig_list: list,
    view_store: dict | None,
    shapes_store: dict | None,
    scalebar_store: dict | None = None,
):
    """Build image figures: new panels, a refreshed panel, or a reset of the
    shared view.

    Zooms, tool changes, box annotations and colormap picks are deliberately
    *not* inputs here: every call ships the full figures (image data included)
    to the server and back, so those go through the lightweight
    ``sync_image_views`` and ``recolor_image`` instead. Whatever is built here
    is put into the shared view so it lands in step with the other panels.

    Only single-channel panels (those with an element Apply button) are
    built here; a composite panel is ``update_composite_figure``'s. The reset
    applies to every panel with a figure, whichever kind. The processed-id
    store is only returned when this call added to it, since the composite
    callback writes the same store and may be running at the same time.

    The Apply button of a refreshed panel goes back to idle, and a later
    panel seeded from another's figure is marked pending, since its image
    is a copy rather than what its controls say.
    """

    if "graph_ids" not in processed_graph_store:
        processed_graph_store["graph_ids"] = []
    _ensure_dataset(user_store_dict, sample_name)
    user_store = UserStore(**user_store_dict)
    view = ensure_view(view_store)
    shapes = _active_shapes(shapes_store)
    scalebar = _scalebar(scalebar_store)
    no_updates = [no_update] * len(fig_list)

    triggered_id = ctx.triggered_id
    spectraLogger.info(f"update_graph_figure triggered by {ctx.triggered_prop_ids}")
    if triggered_id is None or not _valid_sample_name(sample_name):
        return no_updates, no_update, no_update

    # Panels in the layout without a figure yet. Inserting a panel fires this
    # callback (its refresh button is an input), but which of the new inputs
    # ctx reports as the trigger is not worth relying on.
    single_indices = {refresh_id["index"] for refresh_id in refresh_ids}
    new_positions: list[int] = []
    for active_div in graph_id_store.get("active_div_ids", []):
        pos = _find_id_in_list(_imageIDS.graph, active_div["index"], graph_ids)
        if (
            pos is not None
            and active_div["index"] in single_indices
            and _graph_dict(active_div["index"])
            not in processed_graph_store["graph_ids"]
        ):
            new_positions.append(pos)

    if new_positions:
        spectraLogger.info(f"building figures for panels at {new_positions}")
        md = user_store.conditionally_fetch_metadata()
        assert md is not None

        # On the first pass every panel needs its own image, and those fetches
        # are the slow part -- run them concurrently. A panel added later is
        # seeded from an existing figure and fetches nothing until refreshed.
        seed = next((fig for fig in fig_list if fig and fig.get("data")), None)
        im_arrays: list[npt.NDArray]
        if seed is not None:
            im_arrays = [plotly_im_trace_to_array(seed["data"][0])] * len(new_positions)
        else:
            im_arrays = list(
                fetch_im_data_parallel(
                    user_store,
                    [slider_range_list[pos] for pos in new_positions],
                    md,
                )
            )

        new_figs = list(no_updates)
        for pos, im_array in zip(new_positions, im_arrays, strict=True):
            colormap = colormap_choices[pos]
            assert isinstance(colormap, str)
            processed_graph_store["graph_ids"].append(
                _graph_dict(graph_ids[pos]["index"])
            )
            new_figs[pos] = get_new_im(
                user_store,
                slider_range_list[pos],
                colormap,
                im_data=im_array,
                scalebar_handler=scalebar,
                md=md,
                view=view,
                shapes=shapes,
            )
            set_props(graph_ids[pos], {"style": graph_style(im_array.shape)})
            if seed is not None:
                set_props(
                    _apply_button_id(graph_ids[pos]["index"]), APPLY_PENDING_PROPS
                )
        processed_graph_store["initialized"] = True
        return new_figs, processed_graph_store, no_update

    if triggered_id == _RESET_IMAGES_ID and reset_nclicks:
        # back to the full image on every panel, keeping the tool and the box.
        # A layout patch is all it takes, the image data stays in the browser.
        view = ensure_view({"dragmode": view["dragmode"]})
        md = user_store.conditionally_fetch_metadata()
        patches = list(no_updates)
        for pos, graph_id in enumerate(graph_ids):
            if _graph_dict(graph_id["index"]) in processed_graph_store["graph_ids"]:
                patches[pos] = _view_patch(view, md, scalebar)
        return patches, no_update, view

    # Removing a panel also fires this callback, with every remaining panel's
    # inputs reported as triggered. A refresh click reports one.
    if not isinstance(triggered_id, dict) or len(ctx.triggered_prop_ids) != 1:
        return no_updates, no_update, no_update

    pos = _find_id_in_list(_imageIDS.graph, triggered_id["index"], graph_ids)
    if (
        pos is None
        or _graph_dict(triggered_id["index"]) not in processed_graph_store["graph_ids"]
    ):
        return no_updates, no_update, no_update
    colormap = colormap_choices[pos]
    assert isinstance(colormap, str)

    # fetch the image for the panel's (possibly new) energy range
    spectraLogger.info(f"refreshing panel {triggered_id}")
    set_props(_apply_button_id(triggered_id["index"]), APPLY_IDLE_PROPS)
    new_figs = list(no_updates)
    new_figs[pos] = get_new_im(
        user_store,
        slider_range_list[pos],
        colormap,
        scalebar_handler=scalebar,
        view=view,
        shapes=shapes,
    )
    return new_figs, no_update, no_update


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure", allow_duplicate=True),
    Output(_IDS.processed_graph_id_store, "data", allow_duplicate=True),
    Input({"type": _compositeIDS.apply, "index": ALL}, "n_clicks"),
    State({"type": _compositeIDS.apply, "index": ALL}, "id"),
    State({"type": channel_selector_ids.dropdown, "index": ALL}, "value"),
    State({"type": channel_selector_ids.dropdown, "index": ALL}, "id"),
    State({"type": channel_selector_ids.slider, "index": ALL}, "value"),
    State({"type": channel_selector_ids.slider, "index": ALL}, "id"),
    State({"type": _channelIDS.color, "index": ALL}, "value"),
    State({"type": _channelIDS.color, "index": ALL}, "id"),
    State({"type": _channelIDS.stretch, "index": ALL}, "value"),
    State({"type": _channelIDS.stretch, "index": ALL}, "id"),
    State(_IDS.graph_id_store, "data"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(USER_STORE_DIV_ID, "data"),
    State(_IDS.processed_graph_id_store, "data"),
    State("sample-name", "children"),
    State(_IDS.view_store, "data"),
    State(_IDS.shapes_store, "data"),
    State(_IDS.scalebar_style_store, "data"),
    running=[
        (Output("full-im-container-loading", "display"), "show", "hide"),
        (Output(_ADD_IMAGE_ID, "disabled"), True, False),
        (Output(_RESET_IMAGES_ID, "disabled"), True, False),
        (Output(_dataExportIDS.exportsummary, "disabled"), True, False),
        (Output(_dataExportIDS.exportmsa, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def update_composite_figure(
    n_clicks: list[int | None],  # noqa: ARG001
    apply_ids: list[dict[str, Any]],
    channel_elements: list[str | None],
    channel_element_ids: list[dict[str, Any]],
    channel_ranges: list[list[float] | None],
    channel_range_ids: list[dict[str, Any]],
    channel_colors: list[str | None],
    channel_color_ids: list[dict[str, Any]],
    channel_stretches: list[list[float] | None],
    channel_stretch_ids: list[dict[str, Any]],
    graph_id_store: dict,
    graph_ids: list[dict[str, str | int]],
    user_store_dict: dict,
    processed_graph_store: dict,
    sample_name: str,
    view_store: dict | None,
    shapes_store: dict | None,
    scalebar_store: dict | None = None,
):
    """Build composite figures: every new composite panel, or the one whose
    Apply was clicked.

    The channel controls arrive as flat ``ALL`` lists and are regrouped per
    panel by ``channel_specs_from_states``. Each active channel's map is
    fetched (all panels' channels concurrently), blended and drawn into the
    shared view. Nothing here reads the existing figures: a composite always
    fetches its own channels. The clicked Apply goes back to idle.
    """
    no_updates = [no_update] * len(graph_ids)
    if not _valid_sample_name(sample_name):
        return no_updates, no_update

    composite_indices = {apply_id["index"] for apply_id in apply_ids}
    processed = list(processed_graph_store.get("graph_ids", []))

    new_indices = [
        active_div["index"]
        for active_div in graph_id_store.get("active_div_ids", [])
        if active_div["index"] in composite_indices
        and _graph_dict(active_div["index"]) not in processed
        and _find_id_in_list(_imageIDS.graph, active_div["index"], graph_ids)
        is not None
    ]
    if new_indices:
        targets = new_indices
    else:
        # a removal reports every remaining Apply as triggered; a click, one
        triggered_id = ctx.triggered_id
        if (
            not isinstance(triggered_id, dict)
            or len(ctx.triggered_prop_ids) != 1
            or triggered_id["index"] not in composite_indices
            or _graph_dict(triggered_id["index"]) not in processed
        ):
            return no_updates, no_update
        targets = [triggered_id["index"]]
        set_props(_composite_apply_id(targets[0]), APPLY_IDLE_PROPS)
    spectraLogger.info(f"building composite figures for panels {targets}")

    _ensure_dataset(user_store_dict, sample_name)
    user_store = UserStore(**user_store_dict)
    md = user_store.conditionally_fetch_metadata()
    assert md is not None
    view = ensure_view(view_store)
    shapes = _active_shapes(shapes_store)

    specs = channel_specs_from_states(
        channel_elements,
        channel_element_ids,
        channel_ranges,
        channel_range_ids,
        channel_colors,
        channel_color_ids,
        channel_stretches,
        channel_stretch_ids,
    )
    jobs = [
        (index, channel)
        for index in targets
        for channel in specs.get(index, [])
        if channel.active
    ]
    arrays: list[npt.NDArray] = []
    if jobs:
        arrays = list(
            fetch_im_data_parallel(
                user_store, [channel.energy_range for _, channel in jobs], md
            )
        )

    new_figs = list(no_updates)
    for index in targets:
        pos = _find_id_in_list(_imageIDS.graph, index, graph_ids)
        assert pos is not None
        panel_arrays = [
            im
            for (job_index, _), im in zip(jobs, arrays, strict=True)
            if job_index == index
        ]
        fig = get_composite_im(
            specs.get(index, []),
            panel_arrays,
            md,
            scalebar_handler=_scalebar(scalebar_store),
            view=view,
            shapes=shapes,
        )
        new_figs[pos] = fig
        set_props(graph_ids[pos], {"style": graph_style(tuple(md.data_shape[:2]))})
        if _graph_dict(index) not in processed:
            processed.append(_graph_dict(index))

    if new_indices:
        processed_graph_store["graph_ids"] = processed
        processed_graph_store["initialized"] = True
        return new_figs, processed_graph_store
    return new_figs, no_update


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure", allow_duplicate=True),
    Input({"type": _imageIDS.colorscale, "index": ALL}, "value"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(_IDS.processed_graph_id_store, "data"),
    prevent_initial_call=True,
)
def recolor_image(
    colormap_choices: list[str | None],
    graph_ids: list[dict[str, str | int]],
    processed_graph_store: dict,
):
    """Swap the colormap of one panel as a layout patch.

    Nothing but the dropdown values comes in, so the image stays in the
    browser. Inserting or removing a panel fires this too (a removal reports
    every remaining dropdown as triggered); a pick reports one, on a panel that
    already has a figure.
    """
    no_updates = [no_update] * len(graph_ids)

    triggered_id = ctx.triggered_id
    if not isinstance(triggered_id, dict) or len(ctx.triggered_prop_ids) != 1:
        return no_updates
    pos = _find_id_in_list(_imageIDS.graph, triggered_id["index"], graph_ids)
    processed = processed_graph_store.get("graph_ids", [])
    if pos is None or _graph_dict(triggered_id["index"]) not in processed:
        return no_updates
    colormap = colormap_choices[pos]
    if not isinstance(colormap, str):
        return no_updates

    spectraLogger.info(f"recoloring panel {triggered_id}")
    patches = list(no_updates)
    patches[pos] = colorscale_patch(colormap)
    return patches


def _view_patch(
    view: dict,
    md: "CombinedMetadata | None",
    scalebar: scalebarHandler | None = None,
) -> Patch:
    """A figure patch moving a panel to the shared view, scalebar included,
    drawn by ``scalebar`` (the toolbox's style) or the default handler."""
    patch = apply_axes_to_patch(Patch(), view)
    if md is not None:
        trace, annotation = (scalebar or scalebar_handler).get_pieces(
            md,
            x_range=sorted_axis_range(view, "xaxis"),
            y_range=sorted_axis_range(view, "yaxis"),
        )
        patch["data"][1] = trace
        patch["layout"]["annotations"][0] = annotation
    return patch


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure", allow_duplicate=True),
    Output(_IDS.view_store, "data"),
    Output(_IDS.shapes_store, "data"),
    Input({"type": _imageIDS.graph, "index": ALL}, "relayoutData"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(_IDS.processed_graph_id_store, "data"),
    State(_IDS.view_store, "data"),
    State(_IDS.shapes_store, "data"),
    State(USER_STORE_DIV_ID, "data"),
    State("sample-name", "children"),
    State(_IDS.scalebar_style_store, "data"),
    prevent_initial_call=True,
)
def sync_image_views(
    relayout_data_list: list[dict | None],
    graph_ids: list[dict[str, str | int]],
    processed_graph_store: dict,
    view_store: dict | None,
    shapes_store: dict | None,
    user_store_dict: dict,
    sample_name: str,
    scalebar_store: dict | None = None,
):
    """Mirror a zoom, pan, tool change or box annotation onto every panel.

    Only ``relayoutData`` comes in and only layout patches go out, so the image
    data never leaves the browser and the other panels follow almost at once.
    The shared view is rebuilt from the relayout keys rather than read off the
    figure, which does not carry plotly's zoom ranges (issue #65).
    """
    no_updates = [no_update] * len(relayout_data_list)
    nothing = (no_updates, no_update, no_update)

    triggered_id = ctx.triggered_id
    if (
        not isinstance(triggered_id, dict)
        or triggered_id.get("type") != _imageIDS.graph
    ):
        return nothing
    pos = _find_id_in_list(_imageIDS.graph, triggered_id["index"], graph_ids)
    relay = relayout_data_list[pos] if pos is not None else None
    if not relay:
        return nothing

    # Dash only fires a callback when a prop's value changes, and plotly reports
    # every double click as the same {"xaxis.autorange": true, ...} (likewise a
    # re-picked tool). Clear the event once read so the next identical one on
    # this panel still counts as a change.
    set_props(triggered_id, {"relayoutData": None})

    view, axes_changed, dragmode_changed = update_view_from_relayout(view_store, relay)

    def fetch_metadata() -> "CombinedMetadata | None":
        _ensure_dataset(user_store_dict, sample_name)
        return UserStore(**user_store_dict).conditionally_fetch_metadata()

    shapes, shapes_changed, store_shapes = _shapes_after_relayout(
        relay, shapes_store, fetch_metadata
    )
    if not (axes_changed or dragmode_changed or shapes_changed):
        return nothing

    md: CombinedMetadata | None = None
    if axes_changed:
        md = fetch_metadata()

    processed = processed_graph_store.get("graph_ids", [])
    scalebar = _scalebar(scalebar_store)
    patches = list(no_updates)
    for ipos, graph_id in enumerate(graph_ids):
        if _graph_dict(graph_id["index"]) not in processed:
            continue
        patch = _view_patch(view, md, scalebar) if axes_changed else Patch()
        if dragmode_changed:
            patch["layout"]["dragmode"] = view["dragmode"]
        if shapes_changed:
            patch["layout"]["shapes"] = shapes
        patches[ipos] = patch

    return (
        patches,
        view if (axes_changed or dragmode_changed) else no_update,
        {"active_shapes": shapes} if store_shapes else no_update,
    )


def _clicked_index(triggered_id, id_type: str) -> str | None:
    """The ``index`` of the pattern-matched button that fired, or None when
    the trigger is not a real click on a button of that type (a wildcard
    callback also fires when its inputs are inserted with the page)."""
    if not isinstance(triggered_id, dict) or triggered_id.get("type") != id_type:
        return None
    if len(ctx.triggered_prop_ids) != 1 or not ctx.triggered[0]["value"]:
        return None
    index = triggered_id.get("index")
    return index if isinstance(index, str) else None


def _processed_positions(
    graph_ids: list[dict[str, str | int]], processed_graph_store: dict
) -> list[int]:
    processed = processed_graph_store.get("graph_ids", [])
    return [
        pos
        for pos, graph_id in enumerate(graph_ids)
        if _graph_dict(graph_id["index"]) in processed
    ]


def tool_patches(
    tool: str, view: dict | None, graph_ids: list, processed_graph_store: dict
) -> tuple[list, dict]:
    """Put a tool on every panel: the layout patches and the updated view."""
    view = ensure_view(view)
    view["dragmode"] = tool
    patches: list = [no_update] * len(graph_ids)
    for pos in _processed_positions(graph_ids, processed_graph_store):
        patches[pos] = apply_tool_to_patch(Patch(), tool)
    return patches, view


def action_results(
    action: str,
    view: dict | None,
    shapes_store: dict | None,
    graph_ids: list,
    processed_graph_store: dict,
    md: "CombinedMetadata",
    scalebar: scalebarHandler | None = None,
) -> tuple[list, object, object]:
    """The figure patches, view and shapes an action leaves behind (the last
    two ``no_update`` when untouched); a zoom redraws the scalebar with
    ``scalebar``."""
    no_updates: list = [no_update] * len(graph_ids)
    positions = _processed_positions(graph_ids, processed_graph_store)
    nothing = (no_updates, no_update, no_update)
    if not positions:
        return nothing

    if action == "eraseshape":
        if not _active_shapes(shapes_store):
            return nothing
        patches = list(no_updates)
        for pos in positions:
            patch = Patch()
            patch["layout"]["shapes"] = []
            patches[pos] = patch
        return patches, no_update, {"active_shapes": []}

    if action in ZOOM_FACTORS:
        zoomed = zoom_view(ensure_view(view), ZOOM_FACTORS[action], get_image_shape(md))
        patches = list(no_updates)
        for pos in positions:
            patches[pos] = _view_patch(zoomed, md, scalebar)
        return patches, zoomed, no_update

    return nothing


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure", allow_duplicate=True),
    Output(_IDS.view_store, "data", allow_duplicate=True),
    Input({"type": _toolboxIDS.tool, "index": ALL}, "n_clicks"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(_IDS.processed_graph_id_store, "data"),
    State(_IDS.view_store, "data"),
    prevent_initial_call=True,
)
def select_image_tool(
    _n_clicks: list[int | None],
    graph_ids: list[dict[str, str | int]],
    processed_graph_store: dict,
    view_store: dict | None,
):
    """A toolbox tool sets the dragmode of every panel, as a layout patch, and
    is remembered in the shared view so new panels open with it too."""
    tool = _clicked_index(ctx.triggered_id, _toolboxIDS.tool)
    if (
        tool not in IMAGE_TOOLBOX.tool_ids
        or ensure_view(view_store)["dragmode"] == tool
    ):
        return [no_update] * len(graph_ids), no_update
    spectraLogger.info(f"image tool: {tool}")
    return tool_patches(tool, view_store, graph_ids, processed_graph_store)


@callback(
    Output({"type": _toolboxIDS.tool, "index": ALL}, "active"),
    Input(_IDS.view_store, "data"),
    State({"type": _toolboxIDS.tool, "index": ALL}, "id"),
)
def highlight_image_tool(view_store: dict | None, button_ids: list[dict]):
    """The pressed tool button follows the shared view, so it is right however
    the view got there (a click, a reset, a new dataset)."""
    return IMAGE_TOOLBOX.tool_states_for(view_store, button_ids)


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure", allow_duplicate=True),
    Output(_IDS.view_store, "data", allow_duplicate=True),
    Output(_IDS.shapes_store, "data", allow_duplicate=True),
    Input({"type": _toolboxIDS.action, "index": ALL}, "n_clicks"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(_IDS.processed_graph_id_store, "data"),
    State(_IDS.view_store, "data"),
    State(_IDS.shapes_store, "data"),
    State(USER_STORE_DIV_ID, "data"),
    State("sample-name", "children"),
    State(_IDS.scalebar_style_store, "data"),
    prevent_initial_call=True,
)
def run_image_action(
    _n_clicks: list[int | None],
    graph_ids: list[dict[str, str | int]],
    processed_graph_store: dict,
    view_store: dict | None,
    shapes_store: dict | None,
    user_store_dict: dict,
    sample_name: str,
    scalebar_store: dict | None = None,
):
    """Zoom in, zoom out or erase the box on every panel at once.

    Like ``sync_image_views`` this only ever sends layout patches: a zoom step
    is computed on the shared view (an un-zoomed axis spans the whole image,
    whose shape the metadata gives) and the box is simply dropped.
    """
    action = _clicked_index(ctx.triggered_id, _toolboxIDS.action)
    if action is None:
        return [no_update] * len(graph_ids), no_update, no_update
    spectraLogger.info(f"image action: {action}")
    _ensure_dataset(user_store_dict, sample_name)
    md = UserStore(**user_store_dict).conditionally_fetch_metadata()
    assert md is not None
    return action_results(
        action,
        view_store,
        shapes_store,
        graph_ids,
        processed_graph_store,
        md,
        scalebar=_scalebar(scalebar_store),
    )


# The panels' clicks reach the polygon through a document-level listener in
# assets/toolbox.js, which tells a double click from two single ones and
# writes {kind, x, y, n} into the click store; that write is what fires
# edit_polygon. Nothing goes through the graphs' clickData: two identical
# clicks in a row are deduplicated on the way to a Dash callback.


def _visible_spans(view: dict | None, md: "CombinedMetadata") -> tuple[float, float]:
    """How much of the image each axis shows, in pixels: the view's range, or
    the whole image for an axis at its default."""
    image_shape = get_image_shape(md)
    spans = []
    for ax in ("xaxis", "yaxis"):
        rng = sorted_axis_range(view, ax) or sorted(image_axis_range(ax, image_shape))
        spans.append(rng[1] - rng[0])
    return spans[0], spans[1]


def polygon_edit_results(
    click: dict,
    view: dict | None,
    shapes_store: dict | None,
    graph_ids: list,
    processed_graph_store: dict,
    md: "CombinedMetadata",
) -> tuple[list, object]:
    """The figure patches and shapes store a polygon gesture leaves behind.

    A click appends a corner (none when it lands on an existing one), a
    double click removes the corner nearest to it or, failing that, inserts
    a corner on the nearest segment, and a move (the end of a drag in the
    browser) relocates the corner ``index``. Nearness is a fraction of the
    visible extent. The points already submitted are kept, so the spectrum
    stays put until the next Submit shape.
    """
    no_updates: list = [no_update] * len(graph_ids)
    points = polygon_points(shapes_store)
    spans = _visible_spans(view, md)
    tolerance = pick_tolerance(spans)
    x, y = float(click["x"]), float(click["y"])
    kind = click.get("kind")
    if kind == "dblclick":
        new_points = remove_nearest_point(points, x, y, tolerance)
        if new_points == points:
            new_points = insert_point_on_nearest_segment(points, x, y, tolerance)
    elif kind == "move":
        new_points = move_point(points, int(click.get("index", -1)), x, y)
    else:
        new_points = add_point(points, x, y, tolerance)
    if new_points == points:
        return no_updates, no_update

    store = polygon_store(
        new_points, submitted_polygon(shapes_store), vertex_radius_for(spans)
    )
    patches = list(no_updates)
    for pos in _processed_positions(graph_ids, processed_graph_store):
        patch = Patch()
        patch["layout"]["shapes"] = store["active_shapes"]
        patches[pos] = patch
    return patches, store


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure", allow_duplicate=True),
    Output(_IDS.shapes_store, "data", allow_duplicate=True),
    Input(_IDS.polygon_click_store, "data"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(_IDS.processed_graph_id_store, "data"),
    State(_IDS.view_store, "data"),
    State(_IDS.shapes_store, "data"),
    State(USER_STORE_DIV_ID, "data"),
    State("sample-name", "children"),
    prevent_initial_call=True,
)
def edit_polygon(
    click: dict | None,
    graph_ids: list[dict[str, str | int]],
    processed_graph_store: dict,
    view_store: dict | None,
    shapes_store: dict | None,
    user_store_dict: dict,
    sample_name: str,
):
    """Place or remove a polygon corner on every panel, as layout patches.

    A first corner replaces whatever selection was drawn before (a box, or a
    polygon submitted earlier is redrawn from its own points as they change).
    """
    if not click or IMAGE_TOOLBOX.active_tool(view_store) != DRAW_POLYGON.id:
        return [no_update] * len(graph_ids), no_update
    spectraLogger.info(
        f"polygon {click.get('kind')} at {click.get('x')}, {click.get('y')}"
    )
    _ensure_dataset(user_store_dict, sample_name)
    md = UserStore(**user_store_dict).conditionally_fetch_metadata()
    assert md is not None
    return polygon_edit_results(
        click, view_store, shapes_store, graph_ids, processed_graph_store, md
    )


@callback(
    Output(_IDS.shapes_store, "data", allow_duplicate=True),
    Input(_SUBMIT_SHAPE_ID, "n_clicks"),
    State(_IDS.shapes_store, "data"),
    prevent_initial_call=True,
)
def submit_polygon(n_clicks: int | None, shapes_store: dict | None):
    """Submit shape makes the placed corners the selection; ``update_spectrum``
    sees the store change and fetches the spectrum over the polygon."""
    if not n_clicks or not polygon_is_submittable(shapes_store):
        return no_update
    points = polygon_points(shapes_store)
    spectraLogger.info(f"polygon submitted with {len(points)} points")
    return polygon_store(points, points, vertex_radius(shapes_store))


@callback(
    Output(POLYGON_CONTROLS_ID, "hidden"),
    Output(POLYGON_NOTE_ID, "hidden"),
    Output(_SUBMIT_SHAPE_ID, "disabled"),
    Input(_IDS.view_store, "data"),
    Input(_IDS.shapes_store, "data"),
)
def toggle_polygon_controls(view_store: dict | None, shapes_store: dict | None):
    """The how-to note and Submit shape show only while the polygon tool is
    pressed; the button is live once three corners are placed that have not
    been submitted yet."""
    hidden = IMAGE_TOOLBOX.active_tool(view_store) != DRAW_POLYGON.id
    return hidden, hidden, not polygon_is_submittable(shapes_store)


@callback(
    Output(_dataExportIDS.figuresettings, "hidden"),
    Input(_IDS.shapes_store, "data"),
)
def toggle_figure_export_settings(shapes_store: dict | None) -> bool:
    """The figure export settings only matter once a box or a polygon is the
    selection the export would draw; a polygon still being placed is not."""
    return selection_from_store(shapes_store) is None


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure", allow_duplicate=True),
    Output(_IDS.scalebar_style_store, "data"),
    Input(SCALEBAR_SHOW_ID, "value"),
    Input(SCALEBAR_COLOR_ID, "value"),
    Input(SCALEBAR_FONTSIZE_ID, "value"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(_IDS.processed_graph_id_store, "data"),
    prevent_initial_call=True,
)
def restyle_scalebar(
    show: bool | None,
    color: str | None,
    fontsize: float | str | None,
    graph_ids: list[dict[str, str | int]],
    processed_graph_store: dict,
):
    """The toolbox's scalebar controls restyle the bar and its label on every
    built panel, as a layout patch, and are remembered in the scalebar store
    that every figure builder and the export read."""
    style = scalebar_style(show, color, fontsize)
    patches: list = [no_update] * len(graph_ids)
    for pos in _processed_positions(graph_ids, processed_graph_store):
        patches[pos] = apply_style_to_patch(Patch(), style)
    return patches, style.to_store()


@callback(
    Output(_IDS.spectrum_container, "figure", allow_duplicate=True),
    Output(_IDS.spectrum_view_store, "data", allow_duplicate=True),
    Input({"type": _spectrumToolboxIDS.tool, "index": ALL}, "n_clicks"),
    State(_IDS.active_spectrum_metadata, "data"),
    State(_IDS.spectrum_view_store, "data"),
    prevent_initial_call=True,
)
def select_spectrum_tool(
    _n_clicks: list[int | None],
    active_spectrum_metadata: dict | None,
    spectrum_view: dict | None,
):
    """A spectrum tool sets the plot's dragmode as a layout patch and is
    remembered so the figure keeps it when it is next rebuilt.

    The active-spectrum metadata is set in the same callback that draws the
    figure and cleared with it, so it says whether there is a figure to patch
    without uploading the figure itself.
    """
    tool = _clicked_index(ctx.triggered_id, _spectrumToolboxIDS.tool)
    if (
        tool not in SPECTRUM_TOOLBOX.tool_ids
        or SPECTRUM_TOOLBOX.active_tool(spectrum_view) == tool
    ):
        return no_update, no_update
    spectraLogger.info(f"spectrum tool: {tool}")
    view = {"dragmode": tool}
    if not active_spectrum_metadata:
        return no_update, view
    patch = Patch()
    patch["layout"]["dragmode"] = tool
    return patch, view


@callback(
    Output({"type": _spectrumToolboxIDS.tool, "index": ALL}, "active"),
    Input(_IDS.spectrum_view_store, "data"),
    State({"type": _spectrumToolboxIDS.tool, "index": ALL}, "id"),
)
def highlight_spectrum_tool(spectrum_view: dict | None, button_ids: list[dict]):
    return SPECTRUM_TOOLBOX.tool_states_for(spectrum_view, button_ids)


# the zoom steps and the reset act on the plot's live ranges, which only the
# browser has; see assets/toolbox.js
clientside_callback(
    ClientsideFunction("toolbox", "spectrumAction"),
    Output(_IDS.spectrum_action_sink, "data"),
    Input({"type": _spectrumToolboxIDS.action, "index": ALL}, "n_clicks"),
    Input(_SPECTRUM_RESET_ID, "n_clicks"),
    State(_IDS.spectrum_container, "id"),
    prevent_initial_call=True,
)

clientside_callback(
    ClientsideFunction("toolbox", "toggleCollapse"),
    Output(_spectrumToolboxIDS.collapse, "is_open"),
    Output(_spectrumToolboxIDS.chevron, "className"),
    Input(_spectrumToolboxIDS.toggle, "n_clicks"),
    State(_spectrumToolboxIDS.collapse, "is_open"),
    prevent_initial_call=True,
)


@callback(
    Output(USER_STORE_DIV_ID, "data", allow_duplicate=True),
    Output(selectorIDs.get_id_with_index("dropdown"), "options"),
    Output(selectorIDs.get_id_with_index("dropdown"), "value"),
    Output(_IDS.sample_name, "children"),
    Output(_IDS.graph_id_store, "data", allow_duplicate=True),
    Output(_IDS.processed_graph_id_store, "data", allow_duplicate=True),
    Output(_IDS.full_spectrum_store, "data", allow_duplicate=True),
    Output(_IDS.active_spectrum_metadata, "data", allow_duplicate=True),
    Output(_IDS.image_container, "children", allow_duplicate=True),
    Output(_IDS.spectrum_container, "figure"),
    Output(_IDS.view_store, "data", allow_duplicate=True),
    Output(_IDS.spectrum_view_store, "data", allow_duplicate=True),
    Output(_IDS.shapes_store, "data", allow_duplicate=True),
    Output(selectorIDs.get_id_with_index("liststore"), "data", allow_duplicate=True),
    Output(_IDS.image_section, "hidden"),
    Input(selectorIDs.get_id_with_index("dropdown"), "value"),
    Input(selectorIDs.get_id_with_index("refresh"), "n_clicks"),
    State(USER_STORE_DIV_ID, "data"),
    State(selectorIDs.get_id_with_index("dropdown"), "options"),
    State(selectorIDs.get_id_with_index("spectrumonly"), "value"),
    prevent_initial_call=True,
)
def update_selected_dataset(
    input_value: str | None,
    n_clicks: int | None,
    current_user_data: dict,
    current_options,
    spectrum_only_switch: bool | None = False,
):
    """Load a newly picked sample (or refresh the list) and reset the page.

    In spectrum-only mode the image section (toolbox and panels) is hidden
    along the way: the sample is a lone ``.spc`` and there is nothing to image.
    """
    sisi = SpectraInspectorServerInterface()
    trigger = ctx.triggered_id
    dir_sync = UserStore(**current_user_data).directory_sync()
    spectrum_only = resolve_spectrum_only(current_user_data, spectrum_only_switch)

    data_store_selected = current_user_data.get("selected_dataset")
    if input_value is None or (input_value == "none" and data_store_selected):
        input_value = data_store_selected

    valid_clicks = n_clicks or 0
    is_refresh = (
        trigger == selectorIDs.get_id_with_index("refresh") and valid_clicks > 0
    )
    has_input = input_value and input_value != "none"

    available: None | AvailableDatasets = None
    output_lists = no_update
    if is_refresh:
        available = sisi.get_available_datasets(
            refresh_db=True, directory_sync=dir_sync
        )
        output_lists = list_store_data(available)
        names = dataset_names(available, spectrum_only)
        output_options = dropdown_options(names)
        if input_value not in names:
            input_value = None
            has_input = False

    else:
        output_options = current_options

    meta_json_str: str = "{}"
    new_user_data = current_user_data.copy()
    if has_input:
        meta = sisi.get_combined_image_metadata(
            input_value, directory_sync=dir_sync, spectrum_only=spectrum_only
        )
        meta_json_str = meta.model_dump_json()
    new_user_data = updateDataStore(current_user_data, "metadata_json", meta_json_str)

    new_user_data = updateDataStore(new_user_data, "selected_dataset", input_value)
    new_user_data = updateDataStore(new_user_data, "spectrum_only", spectrum_only)

    if new_user_data.get("sample_metadata", None) is None:
        if available is None:
            sample_metadata = sisi.get_available_datasets(
                directory_sync=dir_sync
            ).sample_metadata
        else:
            sample_metadata = available.sample_metadata
        if sample_metadata is not None:
            new_user_data = updateDataStore(
                new_user_data,
                "sample_metadata",
                sample_metadata_for_store(sample_metadata),
            )

    # reset state
    graph_id_store = {"initialized": False}
    processed_graph_id_store = {"initialized": False}
    active_spectrum_metadata = {}
    full_spectrum_store = {}
    figure_div_children = []
    return (
        new_user_data,
        output_options,
        input_value,
        input_value,
        graph_id_store,
        processed_graph_id_store,
        full_spectrum_store,
        active_spectrum_metadata,
        figure_div_children,
        None,
        empty_view(),
        {"dragmode": None},
        {"active_shapes": []},
        output_lists,
        spectrum_only,
    )

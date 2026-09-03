from typing import TYPE_CHECKING, Literal

import dash
import dash_bootstrap_components as dbc
import numpy as np
import numpy.typing as npt
import pandas as pd
import plotly.graph_objects as go
from dash import (
    ALL,
    Input,
    Output,
    Patch,
    State,
    callback,
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
)
from spectra_inspector.components.dataset_selector import format_selections
from spectra_inspector.components.energy_range_slider import elementDropdownSliderIDS
from spectra_inspector.components.scalebar import scalebarHandler
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
    plotly_to_matplotlib,
)
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.summary_writer import summaryWriter
from spectra_inspector.utilities.view_sync import (
    apply_axes_to_patch,
    empty_view,
    ensure_view,
    shapes_from_relayout,
    sorted_axis_range,
    update_view_from_relayout,
)

if TYPE_CHECKING:
    from spectra_inspector.utilities.model import AvailableDatasets, CombinedMetadata

dash.register_page(__name__, order=1, path_template="/inspector/<sample_name>")

NUMBER_OF_INITIAL_FIGURES = 3

scalebar_handler = scalebarHandler()

secondDatasetSelector = datasetSelectorLayoutIDs(index=1)


def _valid_sample_name(sample_name: str | None):
    return (
        sample_name is not None
        and sample_name != "none"
        and isinstance(sample_name, str)
    )


def get_spectrum(
    sample_name: str,
    channel_range: tuple[int, int] | None = None,
    index0_range: tuple[int, int] | None = None,
    index1_range: tuple[int, int] | None = None,
    directory_sync: dict | None = None,
) -> pd.DataFrame:

    sisi = SpectraInspectorServerInterface()
    spectrum = sisi.get_image_spectrum(
        sample_name,
        channel_range=channel_range,
        index0_range=index0_range,
        index1_range=index1_range,
        directory_sync=directory_sync,
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
    add_image: str = "dynamic-add-image-btn"
    reset_all_axes: str = "reset-all-axes"
    metadata: str = "metadata-info"
    sample_name: str = "sample-name"
    image_container: str = "image-container"
    spectrum_container: str = "spectrum-container"
    image_container_type: str = "bitmap-image"
    shapes_store: str = "active-shapes"
    view_store: str = "image-view-store"
    processed_graph_id_store: str = "processed-graph-ids"
    graph_id_store: str = "graph-id-store"
    full_spectrum_store: str = "full-spectrum-store"
    active_spectrum_metadata: str = "active-spectrum-metadata"


_IDS = inspectorIDs()
_imageIDS = bitmapImageLayoutIDs()
_imageSliderIds = elementDropdownSliderIDS()
_dataExportIDS = data_export_panel.dataExportPanelIDS(index=0)


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
            dcc.Store(
                id=_IDS.view_store,  # zoom + tool shared by the image panels
                storage_type="memory",
                data=empty_view(),
            ),
            dcc.Store(id=_IDS.full_spectrum_store, storage_type="memory", data={}),
            dcc.Store(id=_IDS.active_spectrum_metadata, storage_type="memory", data={}),
        ]
    )


selectorIDs = datasetSelectorLayoutIDs(index=1)


def layout(sample_name: str | None = None, **kwargs):  # noqa: ARG001

    _layout_rows = []
    _layout_rows.append(html.Div(hidden=True, id=_IDS.metadata))

    sisi = SpectraInspectorServerInterface()
    _data_selector, _ = dataset_selector(
        sisi, component_index=1, sample_id=sample_name, dropdown_label="Sample: "
    )

    _layout_rows.append(directory_selector(component_index=1))

    image_control_card = dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            _data_selector,
                            width=6,
                            style={"minWidth": 0},
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Add Image",
                                id=_IDS.add_image,
                                n_clicks=0,
                                color="secondary",
                            ),
                            width=3,
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Reset Images",
                                id=_IDS.reset_all_axes,
                                n_clicks=0,
                                color="secondary",
                            ),
                            width=3,
                        ),
                    ],
                    align="top",
                    className="g-4",
                ),
            ]
        )
    )

    _top_image_controls = html.Div(
        [
            image_control_card,
            html.Div(
                selected_sample_contents(sample_name), id=_IDS.sample_name, hidden=True
            ),
        ],
        style={"width": "45%"},
    )

    _layout_rows.append(_top_image_controls)

    im_container = dcc.Loading(
        dbc.Row([], id=_IDS.image_container, className="gx-1 gy-1"),
        id="full-im-container-loading",
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        type="circle",
    )
    # im_container
    _layout_rows.append(im_container)

    spectrum_graph = dcc.Loading(
        dcc.Graph(
            id=_IDS.spectrum_container,
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "scrollZoom": True,
            },
        ),
        id="spectrum-loading",
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        type="circle",
    )

    spectrum_div = dbc.Card(
        dbc.CardBody(dbc.Row(dbc.Col(spectrum_graph, width=12), className="gx-1 gy-1")),
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
    return html.Div(
        _layout_rows,
        className="container",
        style={
            "maxWidth": "6000px",
        },
    )


@callback(
    Output(_IDS.full_spectrum_store, "data", allow_duplicate=True),
    Input(_IDS.sample_name, "children"),
    Input(_IDS.full_spectrum_store, "data"),
    State(USER_STORE_DIV_ID, "data"),
    running=[
        (Output("spectrum-loading", "display"), "show", "hide"),
        (Output(_IDS.add_image, "disabled"), True, False),
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
        df = get_spectrum(
            sample_name,
            directory_sync=UserStore(**(user_store_dict or {})).directory_sync(),
        )
        new_store_data = {}
        new_store_data["intensity"] = df.intensity.tolist()
        new_store_data["energy"] = df.energy.tolist()
        new_store_data["attrs"] = df.attrs
        return new_store_data

    return no_update


@callback(
    Output(_dataExportIDS.elementweightsdiv, "children"),
    Input(
        _IDS.active_spectrum_metadata,
        "data",
    ),
)
def update_element_weights(
    active_spectrum_metadata: dict | None,
):
    if "attrs" in active_spectrum_metadata:
        tble = data_export_panel.get_formatted_element_weights(active_spectrum_metadata)
        return html.Div(tble)
    return html.Div()


@callback(
    Output(_IDS.spectrum_container, "figure", allow_duplicate=True),
    Output(_IDS.active_spectrum_metadata, "data", allow_duplicate=True),
    Input(_IDS.shapes_store, "data"),
    Input(_IDS.full_spectrum_store, "data"),
    State(_IDS.sample_name, "children"),
    State(_IDS.spectrum_container, "figure"),
    State(_IDS.active_spectrum_metadata, "data"),
    State(USER_STORE_DIV_ID, "data"),
    running=[
        (Output("spectrum-loading", "display"), "show", "hide"),
        (Output(_IDS.add_image, "disabled"), True, False),
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
):

    spectraLogger.info(f"update_spectrum trigger: {ctx.triggered_id}")

    if full_spectrum_store is None or "intensity" not in full_spectrum_store:
        # full spectrum data not fetched yet, return
        return no_update, no_update

    if current_figure is None:
        # now we have data but no figure, create it
        energy = full_spectrum_store["energy"]
        intensity = full_spectrum_store["intensity"]
        current_figure = go.Figure()
        current_figure.add_trace(
            go.Scatter(
                x=energy,
                y=intensity,
                mode="lines",
                name="Full energy range",
            )
        )

        current_figure.update_xaxes(title_text="Energy (keV)")
        current_figure.update_yaxes(title_text="Intensity")
        current_figure.update_xaxes(autorangeoptions_maxallowed=8)

        active_spectrum_metadata = full_spectrum_store.copy()

        return current_figure, active_spectrum_metadata

    # finally, we have a figure, but only update if the annotations have changed
    if shapes_store is not None:
        shapes = shapes_store.get("active_shapes", [])
        name = "full spectrum"

        if active_spectrum_metadata is None:
            active_spectrum_metadata = {}

        if len(shapes) > 0:
            assert isinstance(sample_name, str)
            shp = shapes[0]
            index0_range, index1_range = _index_range_from_shape(shp)

            spectraLogger.info(
                f"fetching subsample spectrum with ranges {index0_range}, {index1_range}"
            )
            df = get_spectrum(
                sample_name,
                index0_range=(index0_range[0], index0_range[1]),
                index1_range=(index1_range[0], index1_range[1]),
                directory_sync=UserStore(**(user_store_dict or {})).directory_sync(),
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
        return current_figure, active_spectrum_metadata

    return no_update, no_update


@callback(
    Output(_IDS.add_image, "n_clicks"),
    Input(_IDS.sample_name, "children"),
)
def initial_update(input_value: str | None):
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


def _index_range_from_shape(shp):
    if shp["type"] != "rect":
        msg = f"Unsupported shape type of {shp['type']}"
        raise TypeError(msg)

    index1_range = [int(np.floor(shp["x0"])), int(np.floor(shp["x1"]))]
    index1_range.sort()
    index0_range = [int(np.floor(shp["y0"])), int(np.floor(shp["y1"]))]
    index0_range.sort()
    return index0_range, index1_range


@callback(
    Output(_IDS.image_container, "children", allow_duplicate=True),
    Output(_IDS.graph_id_store, "data", allow_duplicate=True),
    Input(_IDS.add_image, "n_clicks"),
    Input({"type": _imageIDS.delete, "index": ALL}, "n_clicks"),
    State(_IDS.image_container, "children"),
    State(_IDS.graph_id_store, "data"),
    running=[
        (Output(_IDS.add_image, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def add_or_delete_image(
    n_clicks: int | None,
    n_clicks_delete: list[int | None],
    current_children: list[html.Div | None],
    graph_id_store: dict,
):

    button_clicked = ctx.triggered_id
    spectraLogger.info(f"add_or_delete_image button: {button_clicked}")
    n_deletes = sum([n for n in n_clicks_delete if n is not None])

    if "active_div_ids" not in graph_id_store:
        graph_id_store["active_div_ids"] = []

    if button_clicked == _IDS.add_image and n_clicks is not None:
        patched_children = Patch()

        if graph_id_store["initialized"] is False:
            new_index_0 = 0
            new_index_1 = new_index_0 + n_clicks
            graph_id_store["initialized"] = True
        else:
            new_index_0 = n_clicks - 1
            new_index_1 = new_index_0 + 1

        for id_index in range(new_index_0, new_index_1):
            if id_index <= 2:
                init_element_id = id_index
            else:
                init_element_id = 0
            new_image_div, imIDs = bitmap_image_layout(
                id_index,
                id_type_base=_IDS.image_container_type,
                init_element_id=init_element_id,
            )
            patched_children.append(dbc.Col(new_image_div, width=4))
            new_div_id = imIDs.get_id_with_index("div")
            graph_id_store["active_div_ids"].append(new_div_id)
        return patched_children, graph_id_store
    if button_clicked is not None and n_deletes > 0:
        pop_id = _find_id_in_list(
            _imageIDS.div, button_clicked["index"], graph_id_store["active_div_ids"]
        )
        if pop_id is not None:
            _ = current_children.pop(pop_id)
            _ = graph_id_store["active_div_ids"].pop(pop_id)

        return current_children, graph_id_store

    return no_update, graph_id_store


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
):

    if export_clicks is None or export_clicks == 0:
        return None

    if "selected_dataset" not in user_store_dict:
        user_store_dict["selected_dataset"] = sample_name
    user_store = UserStore(**user_store_dict)

    # get individual image arrays
    n_shapes = len(shapes_store["active_shapes"])
    index0_range = None
    index1_range = None
    if n_shapes > 0:
        # get image subests
        shp = shapes_store["active_shapes"][0]
        index0_range, index1_range = _index_range_from_shape(shp)

    figs_to_write = {}
    for igraph in range(len(fig_list)):
        cmap = colormaps[igraph]
        energy_range = slider_range_list[igraph]
        energy_label = slider_range_labels[igraph]

        im_name = f"bitmap_{str(igraph).zfill(2)}"
        if energy_label != "none":
            im_name += f"_{energy_label}"
        figs_to_write[im_name] = plotly_to_matplotlib(fig_list[igraph], cmap=cmap)

        if index0_range and index1_range:
            im = plotly_im_trace_to_array(fig_list[igraph]["data"][0])
            zmin, zmax = np.min(im), np.max(im)
            im = im[
                index0_range[0] : index0_range[1],
                index1_range[0] : index1_range[1],
            ]

            newfig = get_new_im(
                user_store,
                energy_range,
                cmap,
                im,
                scalebar_handler=scalebar_handler,
                zmin=zmin,
                zmax=zmax,
            )

            im_name += "_subset"
            figs_to_write[im_name] = plotly_to_matplotlib(newfig, im_data=im, cmap=cmap)

    figs_to_write["spectrum"] = plotly_to_matplotlib(spectrum_figure)

    s = summaryWriter()
    s.write_static_figures(figs_to_write)

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
            _ = s.write_element_weights(wts)

        return dcc.send_file(s.get_zip())
    msg = f"Unexpected value for format, {export_summary_format=}"
    raise ValueError(msg)


def _graph_dict(index: int) -> dict[str, str | int]:
    return {"type": _imageIDS.graph, "index": index}


def _active_shapes(shapes_store: dict | None) -> list[dict]:
    return list((shapes_store or {}).get("active_shapes", []))


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure"),
    Output(_IDS.processed_graph_id_store, "data"),
    Output(_IDS.view_store, "data", allow_duplicate=True),
    Input({"type": _imageSliderIds.refreshbutton, "index": ALL}, "n_clicks"),
    Input({"type": _imageIDS.colorscale, "index": ALL}, "value"),
    Input(_IDS.reset_all_axes, "n_clicks"),
    State(_IDS.graph_id_store, "data"),
    State({"type": _imageSliderIds.slider, "index": ALL}, "value"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(USER_STORE_DIV_ID, "data"),
    State(_IDS.processed_graph_id_store, "data"),
    State("sample-name", "children"),
    State({"type": _imageIDS.graph, "index": ALL}, "figure"),
    State(_IDS.view_store, "data"),
    State(_IDS.shapes_store, "data"),
    running=[
        (Output("full-im-container-loading", "display"), "show", "hide"),
        (Output(_IDS.add_image, "disabled"), True, False),
        (Output(_IDS.reset_all_axes, "disabled"), True, False),
        (Output(_dataExportIDS.exportsummary, "disabled"), True, False),
        (Output(_dataExportIDS.exportmsa, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def update_graph_figure(
    n_clicks: list[int | None],  # noqa: ARG001
    colormap_choices: list[str | None],
    reset_nclicks: int | None,
    graph_id_store: dict,
    slider_range_list: list[tuple[float, float]],
    graph_ids: list[dict[str, str | int]],
    user_store_dict: dict,
    processed_graph_store: dict,
    sample_name: str,
    fig_list: list,
    view_store: dict | None,
    shapes_store: dict | None,
):
    """Build image figures: new panels, a refreshed panel, a colormap change,
    or a reset of the shared view.

    Zooms, tool changes and box annotations are deliberately *not* inputs here:
    every call ships the full figures (image data included) to the server and
    back, so those go through the lightweight ``sync_image_views`` instead.
    Whatever is built here is put into the shared view so it lands in step
    with the other panels.
    """

    if "graph_ids" not in processed_graph_store:
        processed_graph_store["graph_ids"] = []
    if "selected_dataset" not in user_store_dict:
        user_store_dict["selected_dataset"] = sample_name
    user_store = UserStore(**user_store_dict)
    view = ensure_view(view_store)
    shapes = _active_shapes(shapes_store)
    no_updates = [no_update] * len(fig_list)

    triggered_id = ctx.triggered_id
    spectraLogger.info(f"update_graph_figure triggered by {ctx.triggered_prop_ids}")
    if triggered_id is None or not _valid_sample_name(sample_name):
        return no_updates, processed_graph_store, no_update

    # Panels in the layout without a figure yet. Inserting a panel fires this
    # callback (its colorscale and refresh button are inputs), but which of the
    # new inputs ctx reports as the trigger is not worth relying on.
    new_positions: list[int] = []
    for active_div in graph_id_store.get("active_div_ids", []):
        pos = _find_id_in_list(_imageIDS.graph, active_div["index"], graph_ids)
        if (
            pos is not None
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
                scalebar_handler=scalebar_handler,
                md=md,
                view=view,
                shapes=shapes,
            )
        processed_graph_store["initialized"] = True
        return new_figs, processed_graph_store, no_update

    if triggered_id == _IDS.reset_all_axes and reset_nclicks:
        # back to the full image on every panel, keeping the tool and the box.
        # A layout patch is all it takes, the image data stays in the browser.
        view = ensure_view({"dragmode": view["dragmode"]})
        md = user_store.conditionally_fetch_metadata()
        patches = list(no_updates)
        for pos, graph_id in enumerate(graph_ids):
            if _graph_dict(graph_id["index"]) in processed_graph_store["graph_ids"]:
                patches[pos] = _view_patch(view, md)
        return patches, processed_graph_store, view

    # Removing a panel also fires this callback, with every remaining panel's
    # inputs reported as triggered. A click or a colormap pick reports one.
    if not isinstance(triggered_id, dict) or len(ctx.triggered_prop_ids) != 1:
        return no_updates, processed_graph_store, no_update

    pos = _find_id_in_list(_imageIDS.graph, triggered_id["index"], graph_ids)
    if (
        pos is None
        or _graph_dict(triggered_id["index"]) not in processed_graph_store["graph_ids"]
    ):
        return no_updates, processed_graph_store, no_update
    colormap = colormap_choices[pos]
    assert isinstance(colormap, str)

    refresh = triggered_id["type"] == _imageSliderIds.refreshbutton
    spectraLogger.info(
        f"{'refreshing' if refresh else 'recoloring'} panel {triggered_id}"
    )
    # a colormap change redraws from the image already in the figure; a refresh
    # fetches the image for the panel's (possibly new) energy range.
    im_data = None if refresh else plotly_im_trace_to_array(fig_list[pos]["data"][0])
    new_figs = list(no_updates)
    new_figs[pos] = get_new_im(
        user_store,
        slider_range_list[pos],
        colormap,
        im_data=im_data,
        scalebar_handler=scalebar_handler,
        view=view,
        shapes=shapes,
    )
    return new_figs, processed_graph_store, no_update


def _view_patch(view: dict, md: "CombinedMetadata | None") -> Patch:
    """A figure patch moving a panel to the shared view, scalebar included."""
    patch = apply_axes_to_patch(Patch(), view)
    if md is not None:
        trace, annotation = scalebar_handler.get_pieces(
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
    shapes, shapes_changed = shapes_from_relayout(relay, _active_shapes(shapes_store))
    if not (axes_changed or dragmode_changed or shapes_changed):
        return nothing

    md: CombinedMetadata | None = None
    if axes_changed:
        if "selected_dataset" not in user_store_dict:
            user_store_dict["selected_dataset"] = sample_name
        md = UserStore(**user_store_dict).conditionally_fetch_metadata()

    processed = processed_graph_store.get("graph_ids", [])
    patches = list(no_updates)
    for ipos, graph_id in enumerate(graph_ids):
        if _graph_dict(graph_id["index"]) not in processed:
            continue
        patch = _view_patch(view, md) if axes_changed else Patch()
        if dragmode_changed:
            patch["layout"]["dragmode"] = view["dragmode"]
        if shapes_changed:
            patch["layout"]["shapes"] = shapes
        patches[ipos] = patch

    return (
        patches,
        view if (axes_changed or dragmode_changed) else no_update,
        {"active_shapes": shapes} if shapes_changed else no_update,
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
    Output(_IDS.shapes_store, "data", allow_duplicate=True),
    Input(selectorIDs.get_id_with_index("dropdown"), "value"),
    Input(selectorIDs.get_id_with_index("refresh"), "n_clicks"),
    State(USER_STORE_DIV_ID, "data"),
    State(selectorIDs.get_id_with_index("dropdown"), "options"),
    prevent_initial_call=True,
)
def update_selected_dataset(
    input_value: str | None,
    n_clicks: int | None,
    current_user_data: dict,
    current_options,
):
    sisi = SpectraInspectorServerInterface()
    trigger = ctx.triggered_id
    dir_sync = UserStore(**current_user_data).directory_sync()

    data_store_selected = current_user_data.get("selected_dataset")
    if input_value is None or (input_value == "none" and data_store_selected):
        input_value = data_store_selected

    valid_clicks = n_clicks or 0
    is_refresh = (
        trigger == selectorIDs.get_id_with_index("refresh") and valid_clicks > 0
    )
    has_input = input_value and input_value != "none"

    available: None | AvailableDatasets = None
    if is_refresh:
        available = sisi.get_available_datasets(
            refresh_db=True, directory_sync=dir_sync
        )
        all_files = ["none", *available.available_files]
        output_options = format_selections(all_files)
        if input_value not in output_options:
            input_value = None
            has_input = False

    else:
        output_options = current_options

    meta_json_str: str = "{}"
    new_user_data = current_user_data.copy()
    if has_input:
        meta = sisi.get_combined_image_metadata(input_value, directory_sync=dir_sync)
        meta_json_str = meta.model_dump_json()
    new_user_data = updateDataStore(current_user_data, "metadata_json", meta_json_str)

    new_user_data = updateDataStore(new_user_data, "selected_dataset", input_value)

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
        {"active_shapes": []},
    )

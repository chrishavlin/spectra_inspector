from typing import TYPE_CHECKING, Literal

import dash
import dash_bootstrap_components as dbc
import numpy as np
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
)
from pydantic import BaseModel

from spectra_inspector.components import (
    bitmap_image_layout,
    bitmapImageLayoutIDs,
    data_export_panel,
    dataset_selector,
    datasetSelectorLayoutIDs,
    get_new_im,
)
from spectra_inspector.components.dataset_selector import format_selections
from spectra_inspector.components.energy_range_slider import elementDropdownSliderIDS
from spectra_inspector.components.scalebar import scalebarHandler
from spectra_inspector.logging import spectraLogger
from spectra_inspector.user_store_model import (
    USER_STORE_DIV_ID,
    UserStore,
    updateDataStore,
)
from spectra_inspector.utilities.coerce import (
    copy_layout_attrs,
    copy_layout_attrs_for_new_fig,
    placeholder_to_spaces,
    plotly_im_trace_to_array,
    sync_layouts,
)
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.summary_writer import summaryWriter

if TYPE_CHECKING:
    from spectra_inspector.utilities.model import AvailableDatasets

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
) -> pd.DataFrame:

    sisi = SpectraInspectorServerInterface()
    spectrum = sisi.get_image_spectrum(
        sample_name,
        channel_range=channel_range,
        index0_range=index0_range,
        index1_range=index1_range,
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
            dbc.Col(data_export_panel.get_layout()[0], width=6),
            dbc.Col([], width=6),
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
    running=[
        (Output("spectrum-loading", "display"), "show", "hide"),
        (Output(_IDS.add_image, "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def initialize_full_spectrum_data(sample_name: str | None, spectrum_store: dict | None):

    has_data = isinstance(spectrum_store, dict) and "intensity" in spectrum_store

    if _valid_sample_name(sample_name) and not has_data:
        spectraLogger.info("fetching and storing full spectrum data")
        assert isinstance(sample_name, str)
        df = get_spectrum(sample_name)
        new_store_data = {}
        new_store_data["intensity"] = df.intensity.tolist()
        new_store_data["energy"] = df.energy.tolist()
        new_store_data["attrs"] = df.attrs
        return new_store_data

    return no_update


@callback(
    Output(_IDS.spectrum_container, "figure", allow_duplicate=True),
    Output(_IDS.active_spectrum_metadata, "data", allow_duplicate=True),
    Input(_IDS.shapes_store, "data"),
    Input(_IDS.full_spectrum_store, "data"),
    State(_IDS.sample_name, "children"),
    State(_IDS.spectrum_container, "figure"),
    State(_IDS.active_spectrum_metadata, "data"),
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
        figs_to_write[im_name] = fig_list[igraph]

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
            figs_to_write[im_name] = newfig

    figs_to_write["spectrum"] = spectrum_figure

    s = summaryWriter()
    s.write_static_figures(figs_to_write)

    if export_summary_format == "PDF":
        return dcc.send_file(s.get_pdf_path(generate_pdf=True))
    if export_summary_format == ".zip" and active_spectrum_metadata is not None:
        # include the MSA for the zip
        _ = s.write_MSA(active_spectrum_metadata, file_format=msafileformat)
        return dcc.send_file(s.get_zip())
    msg = f"Unexpected value for format, {export_summary_format=}"
    raise ValueError(msg)


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure"),
    Output(_IDS.processed_graph_id_store, "data"),
    Output(_IDS.shapes_store, "data"),
    Input({"type": _imageSliderIds.refreshbutton, "index": ALL}, "n_clicks"),
    Input({"type": _imageIDS.graph, "index": ALL}, "relayoutData"),
    Input({"type": _imageIDS.colorscale, "index": ALL}, "value"),
    Input(_IDS.reset_all_axes, "n_clicks"),
    State(_IDS.graph_id_store, "data"),
    State({"type": _imageSliderIds.slider, "index": ALL}, "value"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(USER_STORE_DIV_ID, "data"),
    State(_IDS.processed_graph_id_store, "data"),
    State("sample-name", "children"),
    State({"type": _imageIDS.graph, "index": ALL}, "figure"),
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
    n_clicks: list[int | None],
    relayout_data_list: list,
    colormap_choices: list[str | None],
    reset_nclicks: int | None,
    graph_id_store: dict,
    slider_range_list: list[tuple[float, float]],
    graph_ids: list[dict[str, str | int]],
    user_store_dict: dict,
    processed_graph_store: dict,
    sample_name: str,
    fig_list: list,
    shapes_store: dict,
):

    if "graph_ids" not in processed_graph_store:
        processed_graph_store["graph_ids"] = []
    if "active_shapes" not in shapes_store:
        shapes_store["active_shapes"] = []
    if "selected_dataset" not in user_store_dict:
        user_store_dict["selected_dataset"] = sample_name
    user_store = UserStore(**user_store_dict)

    triggered_id = ctx.triggered_id

    if triggered_id is None:
        spectraLogger.info(f"no trigger id, initial call passthrough {len(fig_list)}")
        return (
            [
                no_update,
            ]
            * len(fig_list),
            processed_graph_store,
            shapes_store,
        )

    colorscale_changed = (
        "type" in triggered_id and triggered_id["type"] == _imageIDS.colorscale
    )
    reset_axis_button_clicked = (
        triggered_id == _IDS.reset_all_axes and reset_nclicks is not None
    )
    if colorscale_changed or reset_axis_button_clicked:
        new_list = _recopy_all_figs(
            fig_list,
            user_store,
            slider_range_list,
            colormap_choices,
        )
        new_list = copy_layout_attrs(new_list, fig_list[0], layout_attrs=["shapes"])

        return new_list, processed_graph_store, shapes_store

    triggered_index: int = 0  # the html id index
    triggered_index_loc: int = 0  # the position in the list
    if triggered_id is not None:
        # find the position in the input lists
        triggered_index = triggered_id["index"]
        index_loc = _find_id_in_list(_imageIDS.graph, triggered_index, graph_ids)
        assert isinstance(index_loc, int)
        triggered_index_loc = index_loc

    graph_dict = {"type": _imageIDS.graph, "index": triggered_index}

    # check for figure refresh
    colormap = colormap_choices[triggered_index_loc]
    assert isinstance(colormap, str)
    refresh = triggered_id["type"] == _imageSliderIds.refreshbutton
    if (
        refresh
        and _valid_sample_name(sample_name)
        and graph_dict in processed_graph_store["graph_ids"]
    ):
        spectraLogger.info(
            f"refreshing image id {triggered_id}, {n_clicks[triggered_index_loc]}"
        )
        new_fig = get_new_im(
            user_store,
            slider_range_list[triggered_index_loc],
            colormap,
            scalebar_handler=scalebar_handler,
        )
        fig_list[triggered_index_loc] = new_fig
        fig_list = copy_layout_attrs_for_new_fig(fig_list, triggered_index_loc)
        return fig_list, processed_graph_store, shapes_store

    graph_triggered = triggered_id["type"] == _imageIDS.graph
    if graph_triggered:
        # add new figures!
        initialized = processed_graph_store["initialized"]

        new_graph_dicts = []
        active_divs = graph_id_store["active_div_ids"]
        div_index_to_list_index = {
            active_div["index"]: idiv for idiv, active_div in enumerate(active_divs)
        }

        if initialized is False:
            for active_div in active_divs:
                gdict = {"type": _imageIDS.graph, "index": active_div["index"]}
                if gdict not in processed_graph_store["graph_ids"]:
                    new_graph_dicts.append(gdict)
        elif graph_dict not in processed_graph_store["graph_ids"]:
            new_graph_dicts.append({"type": _imageIDS.graph, "index": triggered_index})

        if len(new_graph_dicts) > 0:
            for graph_dict in new_graph_dicts:
                processed_graph_store["graph_ids"].append(graph_dict)
                im_array = None
                if len(processed_graph_store["graph_ids"]) > 1 and initialized:
                    # we had at least 1 already, data from one to initialize
                    fig = fig_list[0]
                    im_array = plotly_im_trace_to_array(fig["data"][0])

                list_pos = div_index_to_list_index[graph_dict["index"]]
                new_fig = get_new_im(
                    user_store,
                    slider_range_list[list_pos],
                    colormap,
                    im_data=im_array,
                    scalebar_handler=scalebar_handler,
                )
                fig_list[list_pos] = new_fig

                if initialized:
                    fig_list = copy_layout_attrs_for_new_fig(
                        fig_list, triggered_index_loc
                    )

            processed_graph_store["initialized"] = True
            return fig_list, processed_graph_store, shapes_store

        # finally, sync a number of relayouts
        relay = relayout_data_list[triggered_index_loc]
        relay_update = {}
        update_layout = False

        # copy over these keys
        for relay_key in ["shapes", "dragmode"]:
            if relay_key in relay:
                update_layout = True
                relay_update[relay_key] = relay[relay_key]

        if "shapes" in relay_update:
            if len(relay_update["shapes"]) > 1:
                # keep only the latest
                relay_update["shapes"] = [
                    relay_update["shapes"][-1],
                ]
            shapes_store["active_shapes"] = relay_update["shapes"]

        # handle any updates to axes by copying over the modified
        # axis to all others
        joined_relay_keys = " ".join(relay.keys())
        for ax in ["xaxis", "yaxis"]:
            if ax in joined_relay_keys:
                relay_update[ax] = fig_list[triggered_index_loc]["layout"][ax]
                update_layout = True

        # apply the layout updates
        if update_layout:
            # sync once to get layout synced across
            new_fig_list = sync_layouts(relay_update, fig_list)

            # update the scalebar trace
            md = user_store.conditionally_fetch_metadata()
            if md is not None:
                for fig in new_fig_list:
                    scalebar_handler.add_to_or_update_figure(fig, md)
                # sync again as the ranges can get adjusted when adding a trace
                new_fig_list = sync_layouts(relay_update, new_fig_list)
            return new_fig_list, processed_graph_store, shapes_store

    return (
        [
            no_update,
        ]
        * len(fig_list),
        processed_graph_store,
        shapes_store,
    )


def _recopy_all_figs(fig_list, user_store, slider_range_list, colormap_choices):
    """
    refreshes all figures without fetching data again.
    """
    new_list = []
    for igraph in range(len(fig_list)):
        im_array = plotly_im_trace_to_array(fig_list[igraph]["data"][0])
        new_fig = get_new_im(
            user_store,
            slider_range_list[igraph],
            colormap_choices[igraph],
            im_data=im_array,
            scalebar_handler=scalebar_handler,
        )
        new_list.append(new_fig)
    return new_list


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
        available = sisi.get_available_datasets(refresh_db=True)
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
        meta = sisi.get_combined_image_metadata(input_value)
        meta_json_str = meta.model_dump_json()
    new_user_data = updateDataStore(current_user_data, "metadata_json", meta_json_str)

    new_user_data = updateDataStore(new_user_data, "selected_dataset", input_value)

    if new_user_data.get("sample_metadata", None) is None:
        if available is None:
            sample_metadata = sisi.get_available_datasets().sample_metadata
        else:
            sample_metadata = available.sample_metadata
        if sample_metadata is not None:
            new_user_data = updateDataStore(
                new_user_data, "sample_metadata", sample_metadata
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
    )

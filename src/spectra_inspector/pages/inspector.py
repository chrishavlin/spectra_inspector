import dash
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import (
    ALL,
    MATCH,
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
from dash_bootstrap_components import Button
from pydantic import BaseModel

from spectra_inspector.components import bitmap_image_layout, bitmapImageLayoutIDs
from spectra_inspector.logging import spectraLogger
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, UserStore
from spectra_inspector.utilities.coerce import placeholder_to_spaces
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.scaling import get_closest_index

dash.register_page(__name__, order=1, path_template="/inspector/<sample_name>")


def _valid_sample_name(sample_name: str | None):
    return (
        sample_name is not None
        and sample_name != "none"
        and isinstance(sample_name, str)
    )


def get_spectrum(sample_name: str, 
                channel_range: tuple[int, int] | None = None,
                index0_range: tuple[int, int] | None = None,
                index1_range: tuple[int, int] | None = None,
        ) -> pd.DataFrame:

    sisi = SpectraInspectorServerInterface()
    spectrum = sisi.get_image_spectrum(sample_name, 
                                       channel_range=channel_range, 
                                       index0_range=index0_range, 
                                       index1_range=index1_range)

    min_e = spectrum.energy_min
    max_e = spectrum.energy_max
    sz = len(spectrum.energy)
    e_diff = max_e - min_e
    spectraLogger.info(f"fetched spectrum with size {sz}, {min_e=}, {max_e=}")
    dx = e_diff / sz
    energy_scaled = np.arange(sz) * dx + min_e
    return pd.DataFrame({"intensity": spectrum.intensity, "energy": energy_scaled})


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
    metadata: str = "metadata-info"
    sample_name: str = "sample-name"
    image_container: str = "image-container"
    spectrum_container: str = "spectrum-container"
    image_container_type: str = "bitmap-image"
    shapes_store: str = "active-shapes"
    processed_graph_id_store: str = "processed-graph-ids"
    graph_id_store: str = "graph-id-store"
    full_spectrum_store: str = "full-spectrum-store"


_IDS = inspectorIDs()
_imageIDS = bitmapImageLayoutIDs()


def get_initial_figure(sample_name: str | None):
    if _valid_sample_name(sample_name):
        spectraLogger.info("creating full spectrum plot")
        assert isinstance(sample_name, str)
        df = get_spectrum(sample_name)
        current_figure = go.Figure()
        current_figure.add_trace(go.Scatter(x=df.energy, y=df.intensity,
                    mode='lines',
                    name='Full energy range')
                    )
        return {'figure': current_figure}, df
    return {}, None
 

def layout(sample_name: str | None = None, **kwargs):  # noqa: ARG001

    _layout_list = []
    _layout_list.append(
        html.Div(selected_sample_contents(sample_name), id=_IDS.sample_name)
    )
    _layout_list.append(html.Div(hidden=True, id=_IDS.metadata))

    _layout_list.append(
        html.Div(
            [
                Button("Add Image", id=_IDS.add_image, n_clicks=0),
            ]
        )
    )

    im_container = html.Div(
        [html.Div([], id=_IDS.image_container, className="row")], className="container"
    )
    # im_container
    _layout_list.append(
        im_container
    )

    spectrum_kwargs, full_spectrum_df = get_initial_figure(sample_name)    
    spectrum_graph = dcc.Graph(id=_IDS.spectrum_container, **spectrum_kwargs)
    
            
    spectrum_div = html.Div([spectrum_graph], className="container", style={"padding": "10px"})

    init_data = {}
    if full_spectrum_df is not None:
        init_data['intensity'] = full_spectrum_df.intensity.tolist()
        init_data['energy'] = full_spectrum_df.energy.tolist()

    
    
    _layout_list.append(
        html.Div(
            [
                dcc.Store(
                    id=_IDS.graph_id_store,
                    storage_type="memory",
                    data={},
                ),
                dcc.Store(
                    id=_IDS.processed_graph_id_store,
                    storage_type="memory",
                    data={},
                ),
                dcc.Store(
                    id=_IDS.shapes_store,
                    storage_type="memory",
                    data={},
                ),
                dcc.Store(
                    id=_IDS.full_spectrum_store, 
                    storage_type='memory',
                    data = init_data
                )
            ]
        )
    )
    
    _layout_list.append(spectrum_div)
    return html.Div(_layout_list)


@callback(
    Output(_IDS.spectrum_container, "figure"),    
    Input(_IDS.shapes_store, "data"),
    State(_IDS.sample_name, 'children'),
    State(_IDS.spectrum_container, 'figure'),
    State(_IDS.full_spectrum_store, 'data')
)
def update_spectrum(shapes_store: dict | None, 
                    sample_name: str | None, 
                    current_figure, 
                    full_spectrum_store):
            
    if current_figure is None and _valid_sample_name(sample_name):   
        spectraLogger.info("creating full spectrum plot")
        assert isinstance(sample_name, str)
        df = get_spectrum(sample_name)
        current_figure = go.Figure()
        current_figure.add_trace(go.Scatter(x=df.energy, y=df.intensity,
                    mode='lines',
                    name='Full energy range')
                    )            
        return current_figure
    elif current_figure is not None:                         
        if shapes_store is not None:
            shapes = shapes_store.get('active_shapes', [])
            spectraLogger.info(f"active shapes {shapes}")
            name = 'full spectrum'
            if len(shapes) > 0:
                assert isinstance(sample_name, str)                
                shp = shapes[0]
                if shp['type'] != 'rect': 
                    raise TypeError(f"Unsupported shape type of {shp['type']}")
                
                index1_range = [int(np.floor(shp['x0'])), int(np.floor(shp['x1']))]
                index1_range.sort()
                index0_range = [int(np.floor(shp['y0'])), int(np.floor(shp['y1']))]
                index0_range.sort()
                
                spectraLogger.info(f"fetching subsample spectrum with ranges {index0_range}, {index1_range}")
                df = get_spectrum(sample_name, 
                                  index0_range=tuple(index0_range), 
                                  index1_range=tuple(index1_range))
                name = 'spatial subset'         
            else: 
                # just re-load the full spectum
                df = full_spectrum_store 

            new_trace = {
                'mode': 'lines', 
                'x': df['energy'],
                'y': df['intensity'],
                'type': 'scatter',
                'name': name,
            }
                    
            current_figure['data'][0] = new_trace
            spectraLogger.info("subsample spectrum")

        return current_figure
            
    return no_update


@callback(
    Output(_IDS.add_image, "n_clicks"),
    Input(_IDS.sample_name, "children"),
)
def initial_update(input_value: str | None):
    if _valid_sample_name(input_value):
        return 1
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


@callback(
    Output(_IDS.image_container, "children"),
    Output(_IDS.graph_id_store, "data"),
    Input(_IDS.add_image, "n_clicks"),
    Input({"type": _imageIDS.delete, "index": ALL}, "n_clicks"),
    State(_IDS.image_container, "children"),
    State(_IDS.graph_id_store, "data"),
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
        spectraLogger.info("adding new image")
        patched_children = Patch()
        id_index = n_clicks - 1  # easier if we use a 0-index
        new_image_div, imIDs = bitmap_image_layout(
            id_index, id_type_base=_IDS.image_container_type
        )
        patched_children.append(new_image_div)
        new_div_id = imIDs.get_id_with_index("div")
        graph_id_store["active_div_ids"].append(new_div_id)
        return patched_children, graph_id_store
    if button_clicked is not None and n_deletes > 0:
        spectraLogger.info(f"delete button  clicked: {button_clicked}")
        pop_id = _find_id_in_list(
            _imageIDS.div, button_clicked["index"], graph_id_store["active_div_ids"]
        )
        if pop_id is not None:
            active_divid = graph_id_store["active_div_ids"][pop_id]
            spectraLogger.info(f"popping {pop_id}: {active_divid}")
            _ = current_children.pop(pop_id)
            _ = graph_id_store["active_div_ids"].pop(pop_id)

        return current_children, graph_id_store

    return no_update, graph_id_store


def _get_new_im(sample_name: str, user_store: dict, slider_range: tuple[float, float]):

    assert isinstance(sample_name, str)
    sisi = SpectraInspectorServerInterface()
    md = UserStore(**user_store).get_metadata()
    if md is None:
        md = sisi.get_combined_image_metadata(sample_name)

    indx0 = get_closest_index(md.axes_by_index[2], slider_range[0])
    indx1 = get_closest_index(md.axes_by_index[2], slider_range[1])
    msg = f"fetching image data: {sample_name}, {indx0}, {indx1}"
    spectraLogger.info(msg)

    imData = sisi.image_data_summed(sample_name, (indx0, indx1))
    im = np.array(imData.image).reshape(imData.shape)

    return px.imshow(im)


def _sync_layouts(layout_update: dict, fig_list: list):

    new_fig_list = []
    for fig in fig_list:
        fig["layout"].update(layout_update)
        new_fig_list.append(fig)
    return new_fig_list


def _copy_layout_attrs(
    fig_list: list, ref_fig_index: int, layout_attrs: list[str] | None = None
):
    if layout_attrs is None:
        layout_attrs = ["xaxis", "yaxis", "shapes"]
    layout_update = {}
    for attr in layout_attrs:
        if attr in fig_list[ref_fig_index]["layout"]:
            layout_update[attr] = fig_list[ref_fig_index]["layout"][attr]
    return _sync_layouts(layout_update, fig_list)


def _copy_layout_attrs_for_new_fig(
    fig_list: list, new_index_loc: int, layout_attrs: list[str] | None = None
):
    if len(fig_list) > 1:
        if new_index_loc == 0:
            ref_index = 1
        else:
            ref_index = 0
        return _copy_layout_attrs(fig_list, ref_index, layout_attrs=layout_attrs)
    return fig_list


@callback(
    Output({"type": _imageIDS.graph, "index": ALL}, "figure"),
    Output(_IDS.processed_graph_id_store, "data"),
    Output(_IDS.shapes_store, 'data'),
    Input({"type": _imageIDS.refresh, "index": ALL}, "n_clicks"),
    Input({"type": _imageIDS.graph, "index": ALL}, "relayoutData"),
    State({"type": _imageIDS.slider, "index": ALL}, "value"),
    State({"type": _imageIDS.graph, "index": ALL}, "id"),
    State(USER_STORE_DIV_ID, "data"),
    State(_IDS.processed_graph_id_store, "data"),
    State("sample-name", "children"),
    State({"type": _imageIDS.graph, "index": ALL}, "figure"),
    State(_IDS.shapes_store, 'data'),
)
def update_graph_figure(
    n_clicks: list[int | None],
    relayout_data_list: list,
    slider_range_list: list[tuple[float, float]],
    graph_ids: list[dict[str, str | int]],
    user_store: dict,
    processed_graph_store: dict,
    sample_name: str,
    fig_list: list,
    shapes_store: dict,
):

    if "graph_ids" not in processed_graph_store:
        processed_graph_store["graph_ids"] = []

    if 'active_shapes' not in shapes_store:        
        shapes_store['active_shapes'] = []

    triggered_id = ctx.triggered_id
    if triggered_id is None:
        # first pass through on callback creation: dont want to prevent
        # first call though?
        spectraLogger.info(f"no trigger id, initial call passthrough {len(fig_list)}")
        return [
            no_update,
        ] * len(fig_list), processed_graph_store, shapes_store

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
    refresh = triggered_id["type"] == _imageIDS.refresh
    if (
        refresh
        and _valid_sample_name(sample_name)
        and graph_dict in processed_graph_store["graph_ids"]
    ):
        spectraLogger.info(
            f"refreshing image id {triggered_id}, {n_clicks[triggered_index_loc]}"
        )
        new_fig = _get_new_im(
            sample_name, user_store, slider_range_list[triggered_index_loc]
        )
        fig_list[triggered_index_loc] = new_fig
        fig_list = _copy_layout_attrs_for_new_fig(fig_list, triggered_index_loc)
        return fig_list, processed_graph_store, shapes_store

    graph_triggered = triggered_id["type"] == _imageIDS.graph
    if graph_triggered:
        # check if we just added this graph
        if graph_dict not in processed_graph_store["graph_ids"]:
            spectraLogger.info(f"processing new graph {graph_dict}")
            processed_graph_store["graph_ids"].append(graph_dict)
            new_fig = _get_new_im(
                sample_name, user_store, slider_range_list[triggered_index_loc]
            )
            fig_list[triggered_index_loc] = new_fig
            fig_list = _copy_layout_attrs_for_new_fig(fig_list, triggered_index_loc)
            return fig_list, processed_graph_store, shapes_store

        # finally, sync a number of relayouts
        relay = relayout_data_list[triggered_index_loc]
        spectraLogger.info(f"relay keys: {relay.keys()}")
        relay_update = {}
        update_layout = False

        # copy over these keys fully
        for relay_key in ["shapes", "dragmode"]:
            if relay_key in relay:
                update_layout = True
                relay_update[relay_key] = relay[relay_key]

        if "shapes" in relay_update:            
            if len(relay_update["shapes"]) > 1:                 
                # keep only the latest
                relay_update["shapes"] = [relay_update["shapes"][-1],]

            shapes_store['active_shapes'] = relay_update["shapes"]            

        # handle any updates to axes by copying over the modified
        # axis to all others
        joined_relay_keys = " ".join(relay.keys())
        for ax in ["xaxis", "yaxis"]:
            if ax in joined_relay_keys:
                relay_update[ax] = fig_list[triggered_index_loc]["layout"][ax]
                update_layout = True

        # apply the layout updates
        if update_layout:
            new_fig_list = _sync_layouts(relay_update, fig_list)
            return new_fig_list, processed_graph_store, shapes_store

    return [
        no_update,
    ] * len(fig_list), processed_graph_store, shapes_store


import dash
import numpy as np
import pandas as pd
import plotly.express as px
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


def get_spectrum(sample_name: str) -> pd.DataFrame:

    sisi = SpectraInspectorServerInterface()
    spectrum = sisi.get_image_spectrum(sample_name)

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


_IDS = inspectorIDs()
_imageIDS = bitmapImageLayoutIDs()


def layout(sample_name: str | None = None, **kwargs):  # noqa: ARG001

    _layout_list = []

    _layout_list.append(
        html.Div(selected_sample_contents(sample_name), id=_IDS.sample_name)
    )
    _layout_list.append(html.Div(hidden=True, id=_IDS.metadata))
    _layout_list.append(
        html.Div(
            dcc.Store(
                id="graph-id-store",
                storage_type="memory",
                data={},
            ),
        )
    )
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
    )  # html.Div([], id=_IDS.image_container, className="container"))

    fig = dcc.Graph(id=_IDS.spectrum_container)
    spectrum_div = html.Div([fig], className="container", style={"padding": "10px"})
    _layout_list.append(spectrum_div)
    return html.Div(_layout_list)


@callback(
    Output(_IDS.spectrum_container, "figure"),
    Input(_IDS.sample_name, "children"),
)
def update_spectrum(input_value: str | None):
    if _valid_sample_name(input_value):
        assert isinstance(input_value, str)
        df = get_spectrum(input_value)
        return px.line(df, x="energy", y="intensity")
    return no_update


@callback(
    Output(_IDS.add_image, "n_clicks"),
    Input(_IDS.sample_name, "children"),
)
def initial_update(input_value: str | None):
    if _valid_sample_name(input_value):
        return 1
    return no_update


@callback(
    Output(_IDS.image_container, "children"),
    Output("graph-id-store", "data"),
    Input(_IDS.add_image, "n_clicks"),
    Input({"type": _imageIDS.delete, "index": ALL}, "n_clicks"),
    State(_IDS.image_container, "children"),
    State("graph-id-store", "data"),
)
def add_or_delete_image(
    n_clicks: int | None,
    n_clicks_delete: list[int | None],
    current_children: list[html.Div | None],
    graph_id_store: dict,
):

    button_clicked = ctx.triggered_id
    spectraLogger.info(f"button was {button_clicked}")
    n_deletes = sum([n for n in n_clicks_delete if n is not None])

    if "active_div_ids" not in graph_id_store:
        graph_id_store["active_div_ids"] = []

    if button_clicked == _IDS.add_image and n_clicks is not None:
        spectraLogger.info("adding new image")
        patched_children = Patch()
        new_image_div, imIDs = bitmap_image_layout(
            n_clicks, id_type_base=_IDS.image_container_type
        )

        patched_children.append(new_image_div)
        graph_id_store["active_div_ids"].append(imIDs.get_id_with_index("div"))
        return patched_children, graph_id_store
    if button_clicked is not None and n_deletes > 0:
        spectraLogger.info(f"delete button  clicked: {button_clicked}")
        id_to_delete = {"index": button_clicked["index"], "type": _imageIDS.div}
        id_to_delete2 = {"type": _imageIDS.div, "index": button_clicked["index"]}

        pop_id: int | None = None
        if id_to_delete in graph_id_store["active_div_ids"]:
            pop_id = graph_id_store["active_div_ids"].index(id_to_delete)
        elif id_to_delete2 in graph_id_store["active_div_ids"]:
            pop_id = graph_id_store["active_div_ids"].index(id_to_delete2)
        else:
            spectraLogger.warning(f"Could not find {id_to_delete}")

        if pop_id is not None:
            spectraLogger.info(
                f"popping {pop_id}: {graph_id_store['active_div_ids'][pop_id]}"
            )
            _ = current_children.pop(pop_id)
            _ = graph_id_store["active_div_ids"].pop(pop_id)

        return current_children, graph_id_store

    return no_update, graph_id_store


@callback(
    Output({"type": _imageIDS.graph, "index": MATCH}, "figure"),
    Input({"type": _imageIDS.refresh, "index": MATCH}, "n_clicks"),
    State({"type": _imageIDS.refresh, "index": MATCH}, "id"),
    State({"type": _imageIDS.slider, "index": MATCH}, "value"),
    State(USER_STORE_DIV_ID, "data"),
    State("sample-name", "children"),
)
def refresh_bitmap_image(
    n_clicks: int,
    id: str,
    slider_range: tuple[float, float],
    user_store: dict,
    sample_name: str,
):

    spectraLogger.info(f"refreshing bitmap image for image id {id}, {n_clicks}")
    if _valid_sample_name(sample_name):
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
        return px.imshow(im)  # pxim.add_annotation?
    return no_update


# @callback(
#     Output({"type": _imageIDS.graph, "index": ALL}, "annotations"),
#     Input({"type": _imageIDS.graph, "index": ALL}, "relayoutData"),
#     prevent_initial_call=True,
# )
# def store_annotations(relayout_data_list,
#                       ):

#     spectraLogger.info(f"new annotation detected. Storing.")

#     shapes = set()
#     has_shapes = False
#     for index, relayout_data in enumerate(relayout_data_list):
#         spectraLogger.info(f"Checking {index}")
#         spectraLogger.info(relayout_data)
#         if 'shapes' in relayout_data:
#             spectraLogger.info(f"{index} has shape")
#             has_shapes = True
#             shape_data = [json.dumps(shp) for shp in relayout_data["shapes"]]
#             shapes = shapes.union(set(shape_data))

#     if has_shapes:
#         spectraLogger.info("at least one has shapes, merging")
#         new_shapes = []
#         for shp in shapes:
#             spectraLogger.info(shp)
#             new_shapes.append(json.loads(shp))

#         # spectraLogger.info(f"merged {len(shapes)} shapes")
#         # new_relay_outs = []
#         # for relayout_data in current_relayout_data_list:
#         #     relayout_data['shapes'] = new_shapes
#         #     new_relay_outs.append(relayout_data)

#         # # spectraLogger.info("new shapes")
#         # # spectraLogger.info(new_relay_outs)

#         return [new_shapes for _ in range(len(relayout_data_list))]

#     spectraLogger.info("no shapes")
#     return [no_update for _ in range(len(relayout_data_list))]
#     # #     if index == id:
#     # #         return {'shapes': relayout_data["shapes"] }

#     # # # return relayout_data
#     # if "shapes" in relayout_data:
#     #     spectraLogger.info("shapes are")
#     #     import json
#     #     spectraLogger.info(json.dumps(relayout_data["shapes"],indent=2))
#     #     return {'shapes': relayout_data["shapes"] }
#     # # else:
#     # #     spectraLogger.info('no shapes in relayout')
#     # #     spectraLogger.info(relayout_data)
#     # return {'shapes': []}

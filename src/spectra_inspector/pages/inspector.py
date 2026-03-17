import dash
from dash import html, dcc, callback, Input, Output, State, Patch, MATCH, ALL
from spectra_inspector.utilities.coerce import placeholder_to_spaces
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
import plotly.express as px
import pandas as pd
import numpy as np
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, UserStore
from spectra_inspector.utilities.scaling import get_closest_index
from dash_bootstrap_components import Button
from spectra_inspector.components import bitmap_image_layout, bitmapImageLayoutIDs
from pydantic import BaseModel

dash.register_page(__name__, order=1,  path_template="/inspector/<sample_name>")

def _valid_sample_name(sample_name: str | None):
    return sample_name is not None and sample_name != 'none' and isinstance(sample_name, str)


def get_spectrum(sample_name: str) -> pd.DataFrame:

    sisi = SpectraInspectorServerInterface()
    spectrum = sisi.get_image_spectrum(sample_name)

    min_e = spectrum.energy_min
    max_e = spectrum.energy_max
    sz = len(spectrum.energy)
    e_diff = max_e - min_e
    print(f"fetched spectrum with size {sz}, {min_e=}, {max_e=}")
    dx = e_diff / sz
    energy_scaled = np.arange(sz) * dx + min_e
    return pd.DataFrame({'intensity':spectrum.intensity,
                         'energy': energy_scaled})


def selected_sample_contents(sample_name:str|None) -> str:
    if _valid_sample_name(sample_name):
        assert isinstance(sample_name, str)
        valid_sample = placeholder_to_spaces(sample_name)
        msg = f"{valid_sample}"
    else:
        msg = "none"
    return msg

class inspectorIDs(BaseModel):
    add_image:str = "dynamic-add-image-btn"
    metadata: str = "metadata-info"
    sample_name: str = "sample-name"
    image_container: str = "image-container"
    spectrum_container: str = "spectrum-container"
    image_container_type: str = "bitmap-image"

_IDS = inspectorIDs()
_imageIDS = bitmapImageLayoutIDs()


def layout(sample_name: str | None =None, **kwargs):

    _layout_list = []

    _layout_list.append(html.Div(selected_sample_contents(sample_name), id=_IDS.sample_name))
    _layout_list.append(html.Div(hidden=True, id=_IDS.metadata))
    _layout_list.append(html.Div([
        Button("Add Image", id=_IDS.add_image, n_clicks=0),
    ]))

    # fig_image = dcc.Graph(id="map-image")

    # energy_range = dcc.RangeSlider(0, 15, step=0.1, value=(1.65, 1.9), id='primary-image-range', className="text-info")

    # _primary_graph_div = html.Div([
    #         html.Div(energy_range, style={'background': '#FFFFFF'}),
    #         Button("Refresh Image", id='primary-image-submit'),
    #         fig_image,

    # ])

    # im0_layout, imageIDs = bitmap_image_layout('bitmap-00')

    _layout_list.append(html.Div([], id=_IDS.image_container))

    fig = dcc.Graph(id=_IDS.spectrum_container)
    _layout_list.append(fig)

    _layout = html.Div(_layout_list)

    return _layout


@callback(
    Output(_IDS.spectrum_container, 'figure'),
    Input(_IDS.sample_name, 'children'),
)
def update_spectrum(input_value: str | None):
    if _valid_sample_name(input_value):
        assert isinstance(input_value, str)
        df = get_spectrum(input_value)
        line = px.line(df, x="energy", y="intensity")
        return line

@callback(
    Output(_IDS.image_container, 'children'), 
    Input(_IDS.add_image, 'n_clicks')
) 
def add_new_image(n_clicks:int) -> Patch:
    patched_children = Patch()
    new_image_div, _ = bitmap_image_layout(n_clicks, 
                                           id_type_base=_IDS.image_container_type)

    patched_children.append(new_image_div)
    return patched_children


@callback(
    Output({'type': _imageIDS.graph, 'index': MATCH}, 'figure'),
    Input({'type': _imageIDS.refresh, 'index': MATCH}, 'n_clicks'),
    State({'type': _imageIDS.refresh, 'index': MATCH}, 'id'),
    State({'type': _imageIDS.slider, 'index': MATCH}, 'value'),
    State(USER_STORE_DIV_ID, 'data'),
    State('sample-name', 'children'),
)
def refresh_bitmap_image(n_clicks: int, 
                   id: str, 
                   slider_range: tuple[float, float],
                   user_store: dict, 
                   sample_name: str,
                   ):
    
    print(f"refreshing bitmap image for image id {id}, {n_clicks}")
    if _valid_sample_name(sample_name):        
        assert isinstance(sample_name, str)
        sisi = SpectraInspectorServerInterface()
        md = UserStore(**user_store).get_metadata()
        if md is None:
            md = sisi.get_combined_image_metadata(sample_name)

        indx0 = get_closest_index(md.axes_by_index[2], slider_range[0])
        indx1 = get_closest_index(md.axes_by_index[2], slider_range[1])
        print("fetching image data", sample_name, indx0, indx1)

        imData = sisi.image_data_summed(sample_name, (indx0, indx1))
        im = np.array(imData.image).reshape(imData.shape)
        return px.imshow(im)


@callback(
    Output({'type': _imageIDS.div, 'index': MATCH}, 'children'),
    Input({'type': _imageIDS.delete, 'index': MATCH}, 'n_clicks'),
    State({'type': _imageIDS.delete, 'index': MATCH}, 'id'),  
    State(_IDS.image_container, 'children'),  
    prevent_initial_call=True,     
)
def delete_bitmap_image(n_clicks: int, 
                   id: str,
                   current_state,     
                   ):
        
    if n_clicks is not None and n_clicks> 0:        
        print(f"deleting bitmap image for image id {id}, {n_clicks}")
        return html.Div([], hidden=True)
    else:
        print(f"not deleting bitmap image for image id {id}, {n_clicks}")
    
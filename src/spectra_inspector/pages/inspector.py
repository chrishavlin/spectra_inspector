import dash
from dash import html, dcc, callback, Input, Output, State
from spectra_inspector.utilities.coerce import placeholder_to_spaces
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
import plotly.express as px
import pandas as pd 
import numpy as np
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, UserStore
from spectra_inspector.utilities.scaling import get_closest_index

dash.register_page(__name__, order=1,  path_template="/inspector/<sample_name>")

def _valid_sample_name(sample_name: str | None):
    return sample_name is not None and sample_name != 'none'


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
        valid_sample = placeholder_to_spaces(sample_name)
        msg = f"{valid_sample}"
    else:
        msg = "none"
    return msg


def layout(sample_name: str | None =None, **kwargs):

    _layout_list = []

    _layout_list.append(html.Div(selected_sample_contents(sample_name), id='sample-name'))
    _layout_list.append(html.Div(hidden=True, id='metadata-info'))    

    fig_image = dcc.Graph(id="map-image")        
    _layout_list.append(fig_image)

    fig = dcc.Graph(id="spectrum-graph")        
    _layout_list.append(fig)
        
    _layout = html.Div(_layout_list)

    return _layout


@callback(
    Output('spectrum-graph', 'figure'),
    Input('sample-name', 'children'),      
)
def update_spectrum(input_value: str | None):    
    if _valid_sample_name(input_value):        
        df = get_spectrum(input_value)        
        line = px.line(df, x="energy", y="intensity")
        return line


@callback(
    Output('map-image', 'figure'),
    Input('sample-name', 'children'),
    State(USER_STORE_DIV_ID, 'data'),        
)
def update_primary_bitmap_image(input_value: str | None, 
                                user_store: dict):

    print(f"updating primary bitmap for {input_value}")
    if _valid_sample_name(input_value):        
        sisi = SpectraInspectorServerInterface()
        md = UserStore(**user_store).get_metadata()
        if md is None:
            md = sisi.get_combined_image_metadata(input_value)

        indx0 = get_closest_index(md.axes_by_index[2], 1.65)
        indx1 = get_closest_index(md.axes_by_index[2], 1.9)
        print("fetching image data", input_value, indx0, indx1)
        
        imData = sisi.image_data_summed(input_value, (indx0, indx1))
        im = np.array(imData.image).reshape(imData.shape)
        print("got image data")
        return px.imshow(im)


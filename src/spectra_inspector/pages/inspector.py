import dash
from dash import html, dcc, callback, Input, Output
from dash_bootstrap_components import RadioItems, Button
from spectra_inspector.utilities.coerce import placeholder_to_spaces
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
import plotly.express as px
import pandas as pd 
import numpy as np

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
    energy_scaled = np.arange(sz) * e_diff + min_e    
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

    fig = dcc.Graph(id="spectrum-graph")        
    _layout_list.append(fig)
        
    _layout = html.Div(_layout_list)

    return _layout


@callback(
    Output('spectrum-graph', 'figure'),
    Input('sample-name', 'children'),
)
def update_load_button(input_value: str | None):

    print(input_value)
    if _valid_sample_name(input_value):        
        df = get_spectrum(input_value)        
        line = px.line(df, x="energy", y="intensity")
        return line



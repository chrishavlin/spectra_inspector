import dash
from dash import html, dcc, callback, Input, Output, State
from spectra_inspector.utilities.coerce import placeholder_to_spaces
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
import plotly.express as px
import pandas as pd
import numpy as np
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, UserStore
from spectra_inspector.utilities.scaling import get_closest_index
from dash_bootstrap_components import Button

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


def layout(sample_name: str | None =None, **kwargs):

    _layout_list = []

    _layout_list.append(html.Div(selected_sample_contents(sample_name), id='sample-name'))
    _layout_list.append(html.Div(hidden=True, id='metadata-info'))


    fig_image = dcc.Graph(id="map-image")

    energy_range = dcc.RangeSlider(0, 15, step=0.1, value=(1.65, 1.9), id='primary-image-range', className="text-info")

    _primary_graph_div = html.Div([
            html.Div(energy_range, style={'background': '#FFFFFF'}),
            Button("Refresh Image", id='primary-image-submit'),
            fig_image,

    ])

    _layout_list.append(_primary_graph_div)

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
        assert isinstance(input_value, str)
        df = get_spectrum(input_value)
        line = px.line(df, x="energy", y="intensity")
        return line


@callback(
    Output('map-image', 'figure'),
    Input('sample-name', 'children'),
    Input('primary-image-submit', 'n_clicks'),
    State(USER_STORE_DIV_ID, 'data'),
    State('primary-image-range', 'value')
)
def update_primary_bitmap_image(input_value: str | None,
                                n_clicks: int,
                                user_store: dict,
                                slider_range: list,
                                ):

    print(f"updating primary bitmap for {input_value}, {slider_range=}, {n_clicks=}")
    if _valid_sample_name(input_value):
        assert isinstance(input_value, str)
        sisi = SpectraInspectorServerInterface()
        md = UserStore(**user_store).get_metadata()
        if md is None:
            md = sisi.get_combined_image_metadata(input_value)

        indx0 = get_closest_index(md.axes_by_index[2], slider_range[0])
        indx1 = get_closest_index(md.axes_by_index[2], slider_range[1])
        print("fetching image data", input_value, indx0, indx1)

        imData = sisi.image_data_summed(input_value, (indx0, indx1))
        im = np.array(imData.image).reshape(imData.shape)
        print("got image data")
        return px.imshow(im)


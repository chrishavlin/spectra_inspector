import dash
from dash import html, dcc, callback, Input, Output
from dash_bootstrap_components import RadioItems, Button
from spectra_inspector.utilities.coerce import placeholder_to_spaces

dash.register_page(__name__, order=1,  path_template="/inspector/<sample_name>")


def layout(sample_name: str | None =None, **kwargs):
    if sample_name and sample_name != 'none':
        valid_sample = placeholder_to_spaces(sample_name)
        msg = f"The user requested sample ID: {valid_sample}."
    else:
        msg = "No sample selected"
    return html.Div(msg)

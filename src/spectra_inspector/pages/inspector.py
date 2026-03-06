import dash
from dash import html, dcc, callback, Input, Output
from dash_bootstrap_components import RadioItems, Button


dash.register_page(__name__, order=1,  path_template="/inspector/<sample_name>")


def layout(sample_name: str | None =None, **kwargs):
    if sample_name: 
        msg = f"The user requested sample ID: {sample_name}."
    else:
        msg = "No sample selected"
    return html.Div(msg)

import dash
import dash_bootstrap_components as dbc
from dash import html

dash.register_page(__name__, order=2)

layout = html.Div(
    [
        html.H1("About the project"),
        html.Div(
            [
                "Repositories:",
                dbc.NavLink(
                    "spectra_inspector",
                    href="https://github.com/chrishavlin/spectra_inspector",
                ),
                dbc.NavLink(
                    "spectra_inspector_server",
                    href="https://github.com/chrishavlin/spectra_inspector_server",
                ),
            ]
        ),
    ]
)

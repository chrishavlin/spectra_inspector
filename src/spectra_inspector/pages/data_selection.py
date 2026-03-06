import dash
from dash import html, callback, Input, Output
from dash_bootstrap_components import RadioItems, Button, NavLink
dash.register_page(__name__, path='/', order=0)

layout = html.Div([
    html.H1('Data selection'),
    html.Div([
        "Select a map: ",
        RadioItems(
            options=['C-12','C-40 map 1'],
            value='C-12',
            id='xray-map-name'
        )
    ]),
    html.Br(),
    html.Div(id='metadata-display'),
    html.Div(
        [
            NavLink(Button("Load Selected"), 
                    href=f"/inspector", 
                    ),
        ],
        id="nav-link-loader-div"
    )
])


@callback(
    Output('metadata-display', 'children'),
    Input('xray-map-name', 'value')
)
def update_selected_metadata(input_value):
    return f'You selected: {input_value}'


@callback(
    Output('nav-link-loader-div', 'children'),
    Input('xray-map-name', 'value')
)
def update_selected_metadata(input_value):
    return NavLink(Button("Load Selected"), 
                    href=f"/inspector/{input_value}", 
                    ),
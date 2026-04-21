import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html

from spectra_inspector.components import dataset_selector, sample_map
from spectra_inspector.components.nested_accordian import nested_accordian
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, updateDataStore
from spectra_inspector.utilities.coerce import spaces_to_placeholder
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface

dash.register_page(__name__, path="/", order=0)


def layout(**kwargs) -> html.Div:  # noqa: ARG001

    sisi = SpectraInspectorServerInterface()
    _data_selector = dataset_selector(sisi)

    base_map, _ = sample_map.get_layout()
    base_map_card = dbc.Card(dbc.CardBody(base_map))
    left_panel = dbc.Card(
        dbc.CardBody(
            [
                _data_selector,
                html.Br(),
                html.Div(
                    [
                        dbc.NavLink(
                            dbc.Button("Load Selected"),
                            href="/inspector",
                        ),
                    ],
                    id="nav-link-loader-div",
                ),
                html.Div(id="metadata-display"),
            ]
        )
    )

    _layout = html.Div(
        [
            html.H1("Data selection"),
            html.Div(
                dbc.Row(
                    [
                        dbc.Col(left_panel, width=4),
                        dbc.Col(base_map_card, width=8),
                    ]
                ),
                style={"width": "100%"},
            ),
        ]
    )
    return _layout


@callback(
    Output("nav-link-loader-div", "children"),
    Output("metadata-display", "children"),
    Output(USER_STORE_DIV_ID, "data"),
    Input("data-dropdown", "value"),
    State(USER_STORE_DIV_ID, "data"),
    prevent_initial_call=True,
)
def update_selected_dataset(
    input_value: str | None, current_user_data: dict
) -> tuple[dbc.NavLink, html.Div, dict]:
    sisi = SpectraInspectorServerInterface()

    if input_value is None:
        input_value = "none"

    meta_json_str: str = "{}"
    if input_value and input_value != "none":
        meta = sisi.get_combined_image_metadata(input_value)
        meta_json_str = meta.model_dump_json()
        md = html.Div([html.Hr(), nested_accordian(meta.model_dump())])
    else:
        md = html.Div()

    new_user_data = updateDataStore(current_user_data, "metadata_json", meta_json_str)
    new_user_data = updateDataStore(new_user_data, "selected_dataset", input_value)

    valid_input_vale = spaces_to_placeholder(input_value)
    nl = dbc.NavLink(
        dbc.Button("Load Selected"),
        href=f"/inspector/{valid_input_vale}",
    )

    return nl, md, new_user_data

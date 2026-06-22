import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, no_update

from spectra_inspector.components import dataset_selector, sample_map
from spectra_inspector.components.nested_accordian import nested_accordian
from spectra_inspector.logging import spectraLogger
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, updateDataStore
from spectra_inspector.utilities.coerce import spaces_to_placeholder
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface

dash.register_page(__name__, path="/", order=0)

_basemapIDs = sample_map.sampleMapLayoutIDs()


def layout(**kwargs) -> html.Div:  # noqa: ARG001

    sisi = SpectraInspectorServerInterface()
    _data_selector, available_data = dataset_selector(sisi)

    base_map, _ = sample_map.get_layout(available_data=available_data)
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
    if new_user_data.get("sample_metadata", None) is None:
        available = sisi.get_available_datasets().sample_metadata
        if available is not None:
            new_user_data = updateDataStore(new_user_data, "sample_metadata", available)

    valid_input_vale = spaces_to_placeholder(input_value)

    nl = dbc.NavLink(
        dbc.Button("Load Selected"),
        href=f"/inspector/{valid_input_vale}",
    )

    return nl, md, new_user_data


@callback(
    Output({"type": _basemapIDs.samplemap, "index": 0}, "figure"),
    Input(USER_STORE_DIV_ID, "data"),
    Input({"type": _basemapIDs.dropdown, "index": 0}, "value"),
    State({"type": _basemapIDs.samplemap, "index": 0}, "figure"),
    prevent_initial_call=True,
)
def update_map_figure(
    user_data: dict | None, new_map_style: None | str, current_figure: dict | None
):
    """Handle updates to the map figure triggered by either the user
    store (selection changes) or the map-style dropdown.
    """

    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    if current_figure is None:
        return no_update

    # Determine which input triggered the callback
    triggered = ctx.triggered[-1]["prop_id"].split(".")[0]

    # If the user store triggered, update the selected point highlight
    if triggered == USER_STORE_DIV_ID:
        if not user_data:
            return no_update

        selected = user_data.get("selected_dataset", None)

        try:
            metadata = user_data.get("sample_metadata", None)
            new_fig = sample_map.highlight_selected_point_in_figure(
                current_figure, selected, metadata
            )
        except (RuntimeError, KeyError):
            spectraLogger.exception("Failed to update map selection")
            return no_update
        return new_fig

    # Otherwise, assume the map-style dropdown triggered and update style
    if new_map_style is None:
        return no_update

    try:
        valid_style = sample_map._map_styles[new_map_style]
    except KeyError:
        spectraLogger.exception("Unknown map style requested")
        return no_update

    if current_figure.get("layout", {}).get("map", {}).get("style") == valid_style:
        return no_update

    current_figure.setdefault("layout", {}).setdefault("map", {})["style"] = valid_style
    return current_figure

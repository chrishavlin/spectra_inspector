import dash
from dash import html, callback, Input, Output, State
from dash.dcc import Markdown
from dash_bootstrap_components import Button, NavLink
dash.register_page(__name__, path='/', order=0)
from spectra_inspector.utilities.coerce import spaces_to_placeholder
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.components import dataset_selector
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, updateDataStore


def layout(**kwargs) -> html.Div:

    sisi = SpectraInspectorServerInterface()
    _data_selector = dataset_selector(sisi)
    _layout = html.Div([
        html.H1('Data selection'),
        _data_selector,
        html.Br(),
        html.Div(
            [
                NavLink(Button("Load Selected"),
                        href=f"/inspector",
                        ),
            ],
            id="nav-link-loader-div"
        ),
        html.Div(id='metadata-display'),
    ])
    return _layout


@callback(
    Output('nav-link-loader-div', 'children'),
    Output('metadata-display', 'children'),
    Output(USER_STORE_DIV_ID, 'data'),
    Input('data-dropdown', 'value'), 
    State(USER_STORE_DIV_ID, 'data'),
    prevent_initial_call=True,
)
def update_selected_dataset(input_value: str | None,  
                             current_user_data: dict) -> Markdown:
    sisi = SpectraInspectorServerInterface()

    if input_value is None:
        input_value = 'none'
        
    meta_json_str: str = "{}"
    if input_value and input_value != 'none':
        meta = sisi.get_combined_image_metadata(input_value)
        meta_json_str = meta.model_dump_json(indent=4)

        md_str = f"\n #### Metadata for {input_value}"
        md_str += '\n```\n'
        md_str += meta_json_str
        md_str += '\n```\n'

        md = Markdown(md_str)
    else:
        md = Markdown("")
        
    new_user_data = updateDataStore(current_user_data, 'metadata_json', meta_json_str)

    
    valid_input_vale = spaces_to_placeholder(input_value)
    nl = NavLink(Button("Load Selected"),
                    href=f"/inspector/{valid_input_vale}",
                    )
    
    return nl, md, new_user_data

    
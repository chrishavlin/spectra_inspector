import dash
from dash import html, callback, Input, Output
from dash.dcc import Markdown
from dash_bootstrap_components import Button, NavLink
dash.register_page(__name__, path='/', order=0)
from spectra_inspector.utilities.coerce import spaces_to_placeholder
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.components import dataset_selector


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
    Output('metadata-display', 'children'),
    Input('data-dropdown', 'value')
)
def update_selected_metadata(input_value) -> Markdown:
    sisi = SpectraInspectorServerInterface()
    extra = ''
    if input_value and input_value != 'none':
        meta = sisi.get_image_metadata(input_value)
        extra = meta.model_dump_json(indent=4)

        md_str = f"\n #### Metadata for {input_value}"
        md_str += '\n```\n'
        md_str += extra
        md_str += '\n```\n'

        md = Markdown(md_str)
    else:
        md = Markdown("")

    return md


@callback(
    Output('nav-link-loader-div', 'children'),
    Input('data-dropdown', 'value'),
)
def update_load_button(input_value: str | None) -> NavLink:
    if input_value is None:
        input_value = 'none'

    valid_input_vale = spaces_to_placeholder(input_value)
    return NavLink(Button("Load Selected"),
                    href=f"/inspector/{valid_input_vale}",
                    )
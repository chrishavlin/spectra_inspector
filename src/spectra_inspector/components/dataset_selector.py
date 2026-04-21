from dash import html
from dash.dcc import Dropdown

from spectra_inspector.utilities.interface import SpectraInspectorServerInterface


def dataset_selector(sisi: SpectraInspectorServerInterface) -> html.Div:
    _available: list[str] = ["none"]

    if sisi.connected:
        datasets = sisi.get_available_datasets()
        all_data = _available + datasets.available_files
        _menu_items = [
            {
                "label": html.Span([fi], style={"color": "black", "fontSize": 14}),
                "value": fi,
            }
            for fi in all_data
        ]
        _data_selector = html.Div(
            [
                "Select a sample: ",
                Dropdown(
                    _menu_items,
                    id="data-dropdown",
                    placeholder="Select an EDAX set to load",
                ),
            ]
        )
    else:
        _data_selector = html.Div(
            ["Could not connect to spectra_inspector_server backend."]
        )

    return _data_selector

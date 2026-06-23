from dash import html
from dash.dcc import Dropdown

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import AvailableDatasets


class datasetSelectorLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = ("dropdown",)

    def __init__(
        self, id_type_base: str = "data-selector", index: int | None = None
    ) -> None:
        super().__init__(id_type_base, index)

    @property
    def dropdown(self) -> str:
        return self.full_id("-dropdown")


def dataset_selector(
    sisi: SpectraInspectorServerInterface,
    component_index: int = 0,
) -> tuple[html.Div, AvailableDatasets | None]:
    _available: list[str] = ["none"]
    datasets = None

    dataset_selector_IDS = datasetSelectorLayoutIDs(index=component_index)
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
                    id=dataset_selector_IDS.get_id_with_index("dropdown"),
                    placeholder="Select an EDAX set to load",
                ),
            ]
        )
    else:
        _data_selector = html.Div(
            ["Could not connect to spectra_inspector_server backend."]
        )

    return _data_selector, datasets

from typing import Any

from dash import html
from dash.dcc import Dropdown
from dash_bootstrap_components import Button, Col, Row

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

    @property
    def refresh(self) -> str:
        return self.full_id("-refresh")


def _format_selection(value: str) -> dict[str, Any]:
    return {
        "label": html.Span([value], style={"color": "black", "fontSize": 14}),
        "value": value,
    }


def format_selections(values: list[str]) -> list[dict[str, Any]]:
    return [_format_selection(fi) for fi in values]


def dataset_selector(
    sisi: SpectraInspectorServerInterface,
    component_index: int = 0,
    sample_id: str | None = None,
    dropdown_label: str = "Select a sample: ",
) -> tuple[html.Div, AvailableDatasets | None]:
    _available: list[str] = ["none"]
    datasets = None

    dataset_selector_IDS = datasetSelectorLayoutIDs(index=component_index)
    if sisi.connected:
        datasets = sisi.get_available_datasets()

        all_data = _available + datasets.available_files
        _menu_items = format_selections(all_data)
        _data_selector = html.Div(
            [
                Row([Col(dropdown_label, width=8), Col(width=4)]),
                Row(
                    [
                        Col(
                            Dropdown(
                                _menu_items,
                                id=dataset_selector_IDS.get_id_with_index("dropdown"),
                                placeholder="Select an EDAX set to load",
                                value=sample_id,
                                style={"width": "100%"},
                            ),
                            width=10,
                        ),
                        Col(
                            Button(
                                html.I(className="fa fa-refresh"),
                                id=dataset_selector_IDS.get_id_with_index("refresh"),
                                color="secondary",
                                title="Refresh datasets",
                            ),
                            width=2,
                        ),
                    ],
                    align="center",
                    className="g-0",
                ),
            ]
        )
    else:
        _data_selector = html.Div(
            ["Could not connect to spectra_inspector_server backend."]
        )

    return _data_selector, datasets

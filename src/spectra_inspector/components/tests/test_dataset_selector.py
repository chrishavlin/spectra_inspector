from dash import html

from spectra_inspector.components.dataset_selector import dataset_selector
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface


def test_dataset_selector_no_connection():
    sisi = SpectraInspectorServerInterface()
    assert sisi.connected is False
    ds_div = dataset_selector(sisi)
    assert isinstance(ds_div, html.Div)
    assert "children" in ds_div.available_properties
    assert "Could not connect" in ds_div.children[0]

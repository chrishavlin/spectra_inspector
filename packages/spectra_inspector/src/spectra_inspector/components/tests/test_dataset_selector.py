from dash import html, no_update
from dash.dcc import Dropdown, Store
from dash_bootstrap_components import Switch

from spectra_inspector.components.dataset_selector import (
    dataset_names,
    dataset_selector,
    datasetSelectorLayoutIDs,
    dropdown_options,
    hydrate_spectrum_only,
    list_store_data,
    resolve_spectrum_only,
    toggle_spectrum_only,
)
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import AvailableDatasets

LISTING = AvailableDatasets(
    available_files=["C-1"],
    available_spectra=["C-1", "S-1"],
)
LISTS = {"available_files": ["C-1"], "available_spectra": ["C-1", "S-1"]}


def test_dataset_selector_no_connection():
    # pin the port to one nothing can be listening on, so the test does not
    # depend on whether a real backend happens to be running locally
    sisi = SpectraInspectorServerInterface(port=1)
    assert sisi.connected is False
    ds_div, _ = dataset_selector(sisi)
    assert isinstance(ds_div, html.Div)
    assert "children" in ds_div.available_properties
    assert "Could not connect" in ds_div.children[0]


def test_dataset_selector_layout_ids():
    ids = datasetSelectorLayoutIDs(index=1)
    for prop in ids.prop_names:
        assert prop in getattr(ids, prop)
        assert ids.get_id_with_index(prop)["index"] == 1


def _find(component, kind) -> list:
    found = []
    if isinstance(component, kind):
        found.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, list):
        for child in children:
            found.extend(_find(child, kind))
    elif children is not None and not isinstance(children, str):
        found.extend(_find(children, kind))
    return found


def test_dataset_selector_renders_the_mode(mocker):
    sisi = mocker.MagicMock()
    sisi.get_available_datasets.return_value = LISTING

    div, available = dataset_selector(sisi, sample_id="S-1", spectrum_only=True)
    assert available is LISTING

    (dropdown,) = _find(div, Dropdown)
    assert [o["value"] for o in dropdown.options] == ["none", "C-1", "S-1"]
    assert dropdown.value == "S-1"
    (switch,) = _find(div, Switch)
    assert switch.value is True
    (store,) = _find(div, Store)
    assert store.data == LISTS

    div, _ = dataset_selector(sisi, spectrum_only=False)
    (dropdown,) = _find(div, Dropdown)
    # a standalone .spc is never offered as a map
    assert [o["value"] for o in dropdown.options] == ["none", "C-1"]
    (switch,) = _find(div, Switch)
    assert switch.value is False


def test_dataset_names_by_mode():
    assert dataset_names(LISTING, spectrum_only=False) == ["C-1"]
    assert dataset_names(LISTING, spectrum_only=True) == ["C-1", "S-1"]
    assert dataset_names(LISTS, spectrum_only=True) == ["C-1", "S-1"]
    # older servers, or an empty store, have no spectra list at all
    assert dataset_names(AvailableDatasets(available_files=["C-1"]), True) == []
    assert dataset_names({}, spectrum_only=False) == []
    assert dataset_names(None, spectrum_only=True) == []
    assert list_store_data(None) == {"available_files": [], "available_spectra": []}


def test_dropdown_options_start_with_none():
    assert [o["value"] for o in dropdown_options(["a", "b"])] == ["none", "a", "b"]


def test_resolve_spectrum_only_prefers_the_store():
    assert resolve_spectrum_only({"spectrum_only": True}, False) is True
    assert resolve_spectrum_only({"spectrum_only": False}, True) is False
    # nothing written yet: the switch as the page rendered it (from the URL)
    assert resolve_spectrum_only({}, True) is True
    assert resolve_spectrum_only(None, None) is False


def test_hydrate_spectrum_only():
    assert hydrate_spectrum_only({}, {}) is no_update
    assert hydrate_spectrum_only({}, None) is no_update
    assert hydrate_spectrum_only({}, {"spectrum_only": True}) is True
    assert hydrate_spectrum_only({}, {"spectrum_only": False}) is False


def test_toggle_adopts_the_switch_on_a_fresh_store():
    store, options, values = toggle_spectrum_only([True], [LISTS], {})

    assert store["spectrum_only"] is True
    assert [o["value"] for o in options[0]] == ["none", "C-1", "S-1"]
    # whatever the URL selected stays selected
    assert values == [no_update]


def test_toggle_hydration_leaves_the_selection_alone():
    user_data = {"spectrum_only": True, "selected_dataset": "S-1"}
    store, options, values = toggle_spectrum_only([True], [LISTS], user_data)

    assert store is no_update
    assert [o["value"] for o in options[0]] == ["none", "C-1", "S-1"]
    assert values == [no_update]


def test_toggle_flip_clears_the_selection():
    user_data = {
        "spectrum_only": True,
        "selected_dataset": "S-1",
        "metadata_json": "{...}",
    }
    store, options, values = toggle_spectrum_only([False], [LISTS], user_data)

    assert store["spectrum_only"] is False
    # "S-1" meant a spectrum; it is not a map, and "C-1" would mean the map now
    assert store["selected_dataset"] == "none"
    assert store["metadata_json"] == ""
    assert [o["value"] for o in options[0]] == ["none", "C-1"]
    assert values == [None]


def test_toggle_without_a_selector_on_the_page():
    assert toggle_spectrum_only([], [], {}) == (no_update, [], [])


def test_toggle_tolerates_a_missing_list_store():
    _, options, _ = toggle_spectrum_only([True], [None], {})
    assert [o["value"] for o in options[0]] == ["none"]

"""The data selection page's callbacks: the table's rows and selection, the
map link and the round trip to the inspector."""

import importlib
import json

import dash
import pytest
from dash import no_update
from dash._callback_context import context_value
from dash._utils import AttributeDict

from spectra_inspector.components.dataset_selector import list_store_data
from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.utilities.model import (
    AvailableDatasets,
    sampleMetadata,
    sampleMetadataCSVrecord,
)


def _record(sample_id: str, lat: float | None, lon: float | None, sample_type: str):
    return sampleMetadataCSVrecord(
        sample_id=sample_id,
        lat=lat,
        lon=lon,
        elevation=1100.0,
        group_name="Transect",
        sample_type=sample_type,
        description="a rock",
    )


AVAILABLE = AvailableDatasets(
    available_files=["C-12", "C-29 Map 1", "C-29 Map 2"],
    available_spectra=["C-12", "S-1"],
    sample_metadata=sampleMetadata(
        records=[
            _record("C-12", -50.9, -72.9, "Gabbro"),
            _record("C-29", -51.0, -73.0, "Diorite"),
        ],
        map_samples={"C-12": "C-12", "C-29 Map 1": "C-29", "C-29 Map 2": "C-29"},
    ),
)
LISTING = list_store_data(AVAILABLE)


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app  # noqa: F401

    # the module as dash registered it: importing it by its package path would
    # register every callback a second time
    return importlib.import_module(dash.page_registry["pages.data_selection"]["module"])


@pytest.fixture(autouse=True)
def _clear_context():
    yield
    context_value.set(AttributeDict(triggered_inputs=[]))


def _trigger(*triggers: tuple[dict | str, str]) -> None:
    def prop_id(component_id, prop):
        if isinstance(component_id, dict):
            component_id = json.dumps(
                component_id, sort_keys=True, separators=(",", ":")
            )
        return f"{component_id}.{prop}"

    context_value.set(
        AttributeDict(
            triggered_inputs=[{"prop_id": prop_id(*t)} for t in triggers],
            updated_props={},
        )
    )


def _names(rows: list[dict]) -> list[str]:
    return [row["name"] for row in rows]


def test_inspector_href(page):
    assert page.inspector_href("C-12", spectrum_only=False) == "/inspector/C-12"
    assert (
        page.inspector_href("C-12", spectrum_only=True)
        == "/inspector/C-12?spectrum_only=true"
    )
    assert page.inspector_href("C-29 Map 1", False) == "/inspector/C-29%20Map%201"
    assert page.inspector_href(None, spectrum_only=False) == "/inspector/none"


def test_active_dataset_display(page):
    (empty,) = page.active_dataset_display(None, spectrum_only=False)
    assert "No dataset" in empty.children

    _, badge, link = page.active_dataset_display("C-12", spectrum_only=True)
    assert badge.children == "C-12"
    assert link.href == "/inspector/C-12?spectrum_only=true"


def test_sample_summary(page):
    summary = page.sample_summary("C-29 Map 1", LISTING["sample_metadata"])
    line, description = summary.children
    assert line.children == (
        "C-29 Map 1 · sample C-29 · group Transect · Diorite · "
        "-51.00000, -73.00000 · 1100 m"
    )
    assert description.children == "a rock"


def test_sample_summary_without_a_record(page):
    summary = page.sample_summary("X-1", LISTING["sample_metadata"])
    (line,) = summary.children
    assert line.children == "X-1"
    assert page.sample_summary("X-1", None).children[0].children == "X-1"


@pytest.mark.parametrize(
    ("selected_rows", "expected"),
    [
        (None, None),
        ([], None),
        ([{"name": "C-12"}], "C-12"),
        ({"ids": ["C-12"]}, "C-12"),
        ({"ids": []}, None),
    ],
)
def test_selected_row_name(page, selected_rows, expected):
    assert page.selected_row_name(selected_rows) == expected


def test_a_row_picked_in_the_grid_becomes_the_selection(page):
    _trigger((page._GRID_ID, "selectedRows"))
    assert page.sync_table_selection([{"name": "C-12"}], None) == ("C-12", no_update)
    assert page.sync_table_selection([{"name": "C-12"}], "C-12") == (
        no_update,
        no_update,
    )


def test_a_grid_selection_emptied_by_a_filter_keeps_the_dataset(page):
    _trigger((page._GRID_ID, "selectedRows"))
    assert page.sync_table_selection([], "C-12") == (no_update, no_update)


def test_the_grid_follows_the_dropdown(page):
    _trigger((page._DROPDOWN_ID, "value"))
    assert page.sync_table_selection([], "C-12") == (no_update, {"ids": ["C-12"]})
    assert page.sync_table_selection([{"name": "C-12"}], None) == (no_update, [])
    assert page.sync_table_selection([{"name": "C-12"}], "none") == (no_update, [])
    assert page.sync_table_selection({"ids": ["C-12"]}, "C-12") == (
        no_update,
        no_update,
    )
    assert page.sync_table_selection(None, None) == (no_update, no_update)


def test_table_rows_follow_the_mode_and_filters(page):
    _trigger((page._LISTSTORE_ID, "data"))
    rows, selected, groups, types, hidden, _ = page.update_table_rows(
        LISTING, False, None, None, False, [], "C-12"
    )
    assert _names(rows) == ["C-12", "C-29 Map 1", "C-29 Map 2"]
    # a new listing clears the selection elsewhere: nothing is re-selected
    assert selected is no_update
    assert groups == ["Transect"]
    assert types == ["Diorite", "Gabbro"]
    assert hidden is True

    rows, *_ = page.update_table_rows(LISTING, True, None, None, False, [], None)
    assert _names(rows) == ["C-12", "S-1"]


def test_a_filter_change_reselects_the_dataset_when_its_row_is_back(page):
    _trigger((page.tableIDs.get_id_with_index("types"), "value"))
    rows, selected, *_ = page.update_table_rows(
        LISTING, False, None, ["Gabbro"], False, [], "C-29 Map 1"
    )
    assert _names(rows) == ["C-12"]
    assert selected is no_update

    rows, selected, *_ = page.update_table_rows(
        LISTING, False, None, [], False, [], "C-29 Map 1"
    )
    assert selected == {"ids": ["C-29 Map 1"]}


def test_the_map_selection_filters_the_rows_and_shows_its_badge(page):
    _trigger((page._SAMPLEFILTER_ID, "data"))
    rows, _, _, _, hidden, badge = page.update_table_rows(
        LISTING, False, None, None, False, ["C-29"], None
    )
    assert _names(rows) == ["C-29 Map 1", "C-29 Map 2"]
    assert hidden is False
    assert badge == "Map selection: C-29"


def test_table_count(page):
    rows = [{"name": "C-12"}]
    assert page.update_table_count(None, LISTING, False) == "3 datasets"
    assert page.update_table_count(rows, LISTING, False) == "1 of 3 datasets"
    assert page.update_table_count(rows, LISTING, True) == "1 of 2 spectra"
    truncated = {**LISTING, "truncated": True}
    assert "dataset limit" in page.update_table_count(None, truncated, False)


def test_hydrate_selection(page):
    store = {"selected_dataset": "C-29 Map 1"}
    options, value = page.hydrate_selection({}, LISTING, store)
    assert value == "C-29 Map 1"
    assert [o["value"] for o in options] == ["none", *AVAILABLE.available_files]


def test_hydrate_selection_in_spectrum_mode_sends_the_spectrum_list(page):
    store = {"selected_dataset": "S-1", "spectrum_only": True}
    options, value = page.hydrate_selection({}, LISTING, store)
    assert value == "S-1"
    assert [o["value"] for o in options] == ["none", "C-12", "S-1"]


@pytest.mark.parametrize(
    "store",
    [None, {}, {"selected_dataset": "none"}, {"selected_dataset": "not listed"}],
)
def test_hydrate_selection_without_a_listed_selection(page, store):
    assert page.hydrate_selection({}, LISTING, store) == (no_update, no_update)


def test_open_double_clicked_dataset(page):
    assert page.open_double_clicked_dataset({"rowId": "C-12"}, False, {}) == (
        "/inspector/C-12"
    )
    assert page.open_double_clicked_dataset({"rowId": "S-1"}, True, {}) == (
        "/inspector/S-1?spectrum_only=true"
    )
    assert page.open_double_clicked_dataset(None, False, {}) is no_update


def _mock_interface(mocker, page, **attrs):
    sisi = mocker.MagicMock()
    for key, value in attrs.items():
        setattr(sisi, key, value)
    mocker.patch.object(
        page, "SpectraInspectorServerInterface", mocker.MagicMock(return_value=sisi)
    )
    return sisi


def test_refresh_listing(page, mocker):
    sisi = _mock_interface(
        mocker, page, get_available_datasets=mocker.MagicMock(return_value=AVAILABLE)
    )
    store = {"selected_dataset": "C-12", "metadata_json": "{}"}

    listing, options, value, new_store = page.refresh_listing(1, store, False)

    sisi.get_available_datasets.assert_called_once_with(
        refresh_db=True, directory_sync={}
    )
    assert listing == LISTING
    assert [o["value"] for o in options] == ["none", *AVAILABLE.available_files]
    assert value is None
    assert new_store["selected_dataset"] == "none"
    assert new_store["sample_metadata"] == LISTING["sample_metadata"]


def test_refresh_listing_without_a_click(page, mocker):
    sisi = _mock_interface(mocker, page)
    assert page.refresh_listing(0, {}, False) == (no_update,) * 4
    sisi.get_available_datasets.assert_not_called()


def test_update_selected_dataset_clears_the_selection(page, mocker):
    sisi = _mock_interface(mocker, page)
    active, metadata, store = page.update_selected_dataset(None, {}, LISTING, False)

    sisi.get_combined_image_metadata.assert_not_called()
    assert "No dataset" in active[0].children
    assert "Select a dataset" in metadata.children
    assert store["selected_dataset"] is None
    assert store["sample_metadata"] == LISTING["sample_metadata"]


def test_map_click_on_a_sample_with_one_dataset_selects_it(page):
    _trigger((page._MAP_ID, "clickData"))
    click = {"points": [{"curveNumber": 1, "customdata": ["x", "C-12"]}]}
    assert page.filter_table_from_map(None, click, 0, LISTING, [], False, None) == (
        ["C-12"],
        "C-12",
    )


def test_map_click_on_a_sample_with_several_datasets_only_filters(page):
    _trigger((page._MAP_ID, "clickData"))
    click = {"points": [{"curveNumber": 1, "customdata": ["x", "C-29"]}]}
    assert page.filter_table_from_map(None, click, 0, LISTING, [], False, None) == (
        ["C-29"],
        no_update,
    )


def test_map_click_on_an_unknown_point_is_ignored(page):
    _trigger((page._MAP_ID, "clickData"))
    click = {"points": [{"curveNumber": 1, "customdata": ["x", "0"]}]}
    assert page.filter_table_from_map(None, click, 0, LISTING, [], False, None) == (
        no_update,
        no_update,
    )


def test_map_box_selection_filters_and_emptying_it_lifts_the_filter(page):
    _trigger((page._MAP_ID, "selectedData"))
    selected = {
        "points": [
            {"curveNumber": 1, "customdata": ["x", "C-29"]},
            {"curveNumber": 1, "customdata": ["x", "C-12"]},
        ]
    }
    args = (None, 0, LISTING)
    assert page.filter_table_from_map(selected, *args, [], False, None) == (
        ["C-29", "C-12"],
        no_update,
    )
    assert page.filter_table_from_map(selected, *args, ["C-29", "C-12"], False, None)[
        0
    ] is (no_update)
    assert page.filter_table_from_map(None, *args, ["C-29"], False, None) == (
        [],
        no_update,
    )


@pytest.mark.parametrize("trigger", ["clearsamples", "liststore"])
def test_clear_button_and_a_new_listing_lift_the_map_filter(page, trigger):
    if trigger == "clearsamples":
        _trigger((page.tableIDs.get_id_with_index("clearsamples"), "n_clicks"))
    else:
        _trigger((page._LISTSTORE_ID, "data"))
    assert page.filter_table_from_map(
        None, None, 1, LISTING, ["C-29"], False, None
    ) == (
        [],
        no_update,
    )


def test_map_figure_dims_filtered_samples_and_rings_the_active_one(page):
    rows = [{"name": "C-12", "sample_id": "C-12"}]

    fig = page.update_map_figure(LISTING, "Satellite", rows, "C-12", [])
    assert [row[-1] for row in fig.data[1].customdata] == ["C-12", "C-29"]
    assert fig.data[1].selectedpoints == (0,)
    assert list(fig.data[0].lat) == [-50.9]
    assert fig.layout.map.center.lat == -50.9
    assert fig.layout.map.style == "satellite"


def test_map_figure_follows_the_style_and_the_selection(page):
    fig = page.update_map_figure(LISTING, "OpenStreetMap", None, "C-29 Map 1", [])
    assert fig.layout.map.style == "open-street-map"
    assert fig.data[1].selectedpoints is None
    assert fig.layout.map.center.lat == -51.0

    # nothing selected: no ring, and the listing's own center
    fig = page.update_map_figure(LISTING, "OpenStreetMap", None, None, [])
    assert list(fig.data[0].lat) == []
    assert fig.layout.map.center.lat == pytest.approx(-50.95)


def test_map_figure_keeps_the_view_but_not_a_spent_selection_outline(page):
    args = (LISTING, "Satellite", None, None)
    plain = page.update_map_figure(*args, [])
    filtered = page.update_map_figure(*args, ["C-29"])
    # same samples: plotly keeps the user's zoom and pan
    assert plain.layout.uirevision == filtered.layout.uirevision
    # the map filter changed: the outline that set or stood for it goes
    assert plain.layout.selectionrevision != filtered.layout.selectionrevision


def test_map_figure_for_a_listing_without_samples(page):
    fig = page.update_map_figure(list_store_data(None), "Satellite", [], None, [])
    assert len(fig.data[1].lat) == 1


SESSION = {
    "working_directory": "session-a",
    "available_files": AVAILABLE.available_files,
    "available_spectra": AVAILABLE.available_spectra,
    "sample_metadata": LISTING["sample_metadata"],
}


def test_hydrate_selection_reads_the_sessions_listing_before_the_store_has_it(page):
    # desktop mode renders the page empty; the listing store is hydrated by a
    # sibling callback that may not have landed yet
    store = {**SESSION, "selected_dataset": "C-29 Map 1"}
    options, value = page.hydrate_selection({}, list_store_data(None), store)
    assert value == "C-29 Map 1"
    assert [o["value"] for o in options] == ["none", *AVAILABLE.available_files]


def test_update_selected_dataset_keeps_a_sessions_sample_records(page, mocker):
    _mock_interface(mocker, page)
    _, _, store = page.update_selected_dataset(
        None, dict(SESSION), list_store_data(None), False
    )
    assert store["sample_metadata"] == LISTING["sample_metadata"]

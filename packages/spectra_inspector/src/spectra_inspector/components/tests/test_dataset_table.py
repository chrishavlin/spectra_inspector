import dash_ag_grid as dag
import pytest
from dash import dcc

from spectra_inspector.components.dataset_selector import (
    datasetSelectorLayoutIDs,
    list_store_data,
)
from spectra_inspector.components.dataset_table import (
    COLUMN_DEFS,
    count_label,
    dataset_table,
    datasetTableLayoutIDs,
    facet_values,
    filter_rows,
    sample_filter_label,
    table_rows,
)
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import (
    AvailableDatasets,
    sampleMetadata,
    sampleMetadataCSVrecord,
)


def _record(sample_id: str, **kwargs) -> sampleMetadataCSVrecord:
    values = {
        "lat": None,
        "lon": None,
        "elevation": None,
        "group_name": "None",
        "sample_type": "nan",
        "description": "",
    }
    values.update(kwargs)
    return sampleMetadataCSVrecord(sample_id=sample_id, **values)


LISTING = AvailableDatasets(
    available_files=["C-12", "C-29 Map 1", "C-29 Map 2", "X-1"],
    available_spectra=["C-12", "S-1"],
    sample_metadata=sampleMetadata(
        records=[
            _record(
                "C-12",
                lat=-50.9,
                lon=-72.9,
                elevation=180.0,
                group_name="C",
                sample_type="dike",
                description="a dike",
            ),
            _record("C-29", group_name="C", sample_type="host"),
            _record("S-1"),
        ],
        map_samples={
            "C-12": "C-12",
            "C-29 Map 1": "C-29",
            "C-29 Map 2": "C-29",
            "S-1": "S-1",
        },
    ),
)
STORE = list_store_data(LISTING)


def test_layout_ids():
    ids = datasetTableLayoutIDs(index=0)
    for prop in ids.prop_names:
        assert prop in getattr(ids, prop)
        assert ids.get_id_with_index(prop)["index"] == 0


def test_rows_follow_the_listing_order_and_mode():
    assert [r["name"] for r in table_rows(STORE, spectrum_only=False)] == [
        "C-12",
        "C-29 Map 1",
        "C-29 Map 2",
        "X-1",
    ]
    assert [r["name"] for r in table_rows(STORE, spectrum_only=True)] == ["C-12", "S-1"]


def test_rows_carry_the_sample_record():
    row = table_rows(STORE, spectrum_only=False)[0]
    assert row == {
        "name": "C-12",
        "sample_id": "C-12",
        "group_name": "C",
        "sample_type": "dike",
        "description": "a dike",
        "lat": -50.9,
        "lon": -72.9,
        "elevation": 180.0,
    }


def test_several_datasets_share_a_sample():
    rows = table_rows(STORE, spectrum_only=False)
    assert [r["sample_id"] for r in rows[1:3]] == ["C-29", "C-29"]
    assert [r["sample_type"] for r in rows[1:3]] == ["host", "host"]


def test_a_dataset_without_a_record_keeps_a_blank_row():
    row = table_rows(STORE, spectrum_only=False)[3]
    assert row["name"] == "X-1"
    assert {k: v for k, v in row.items() if k != "name"} == {
        "sample_id": "",
        "group_name": "",
        "sample_type": "",
        "description": "",
        "lat": None,
        "lon": None,
        "elevation": None,
    }


def test_stringified_empty_cells_are_blanked():
    row = table_rows(STORE, spectrum_only=True)[1]
    assert row["sample_id"] == "S-1"
    assert row["group_name"] == ""
    assert row["sample_type"] == ""


@pytest.mark.parametrize("listing", [None, {}, list_store_data(None)])
def test_rows_of_an_empty_listing(listing):
    assert table_rows(listing, spectrum_only=False) == []


def test_facet_values_skip_blanks():
    rows = table_rows(STORE, spectrum_only=False)
    assert facet_values(rows, "group_name") == ["C"]
    assert facet_values(rows, "sample_type") == ["dike", "host"]


def _names(rows: list[dict]) -> list[str]:
    return [r["name"] for r in rows]


def test_filter_rows():
    rows = table_rows(STORE, spectrum_only=False)
    assert filter_rows(rows) == rows
    assert _names(filter_rows(rows, groups=["C"])) == [
        "C-12",
        "C-29 Map 1",
        "C-29 Map 2",
    ]
    assert _names(filter_rows(rows, types=["host"])) == ["C-29 Map 1", "C-29 Map 2"]
    assert _names(filter_rows(rows, located_only=True)) == ["C-12"]
    assert _names(filter_rows(rows, samples=["C-29"])) == ["C-29 Map 1", "C-29 Map 2"]
    assert filter_rows(rows, types=["host"], located_only=True) == []


def test_filter_rows_ignores_values_the_listing_does_not_have():
    rows = table_rows(STORE, spectrum_only=False)
    assert filter_rows(rows, groups=["gone"], types=["also gone"]) == rows
    assert _names(filter_rows(rows, types=["gone", "dike"])) == ["C-12"]


def test_count_label():
    assert count_label(4, 4) == "4 datasets"
    assert count_label(2, 4) == "2 of 4 datasets"
    assert count_label(1, 2, spectrum_only=True) == "1 of 2 spectra"
    truncated = count_label(4, 4, truncated=True)
    assert truncated.startswith("4 datasets (the first 4 found")


def test_sample_filter_label():
    assert sample_filter_label(["C-12"]) == "Map selection: C-12"
    assert sample_filter_label(["C-12", "C-29"]) == "Map selection: 2 samples"


def test_dataset_table_no_connection():
    sisi = SpectraInspectorServerInterface(port=1)
    div, available = dataset_table(sisi)
    assert available is None
    assert "Could not connect" in div.children[0]


def test_dataset_table_layout(mocker):
    sisi = mocker.MagicMock()
    sisi.get_available_datasets.return_value = LISTING

    div, available = dataset_table(sisi)
    assert available is LISTING

    selector_ids = datasetSelectorLayoutIDs(index=0)
    by_id = {
        getattr(c, "id", None)["type"]: c
        for c in div._traverse()
        if isinstance(getattr(c, "id", None), dict)
    }

    grid = by_id[datasetTableLayoutIDs().grid]
    assert isinstance(grid, dag.AgGrid)
    assert _names(grid.rowData) == LISTING.available_files
    assert {c["field"] for c in COLUMN_DEFS} == set(grid.rowData[0])

    # the state the selector's shared callbacks write to
    assert by_id[selector_ids.liststore].data == STORE
    dropdown = by_id[selector_ids.dropdown]
    assert isinstance(dropdown, dcc.Dropdown)
    assert [o["value"] for o in dropdown.options] == ["none", *LISTING.available_files]
    assert by_id[selector_ids.spectrumonly].value is False
    assert selector_ids.refresh in by_id

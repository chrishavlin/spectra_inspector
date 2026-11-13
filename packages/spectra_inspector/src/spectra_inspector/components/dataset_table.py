"""The dataset table of the data selection page.

One row per dataset of the current listing, joined to the sample sheet record
of the sample it belongs to, so the listing can be searched, sorted and
filtered on what the sheet says about a sample. A dataset the sheet does not
know still gets a row, with those cells left blank.

The table is another rendering of the dataset selector rather than a second
selector: the listing store, the mode control, the refresh button and the
selection itself carry `datasetSelectorLayoutIDs` ids, so the callbacks the
selector shares with the working-directory picker act on the table unchanged.
The selection is still a (hidden) dropdown, because those callbacks write its
``options`` and ``value``; the grid's selected row is kept in step with it by
the page. The mode control is a two-button group here instead of a switch, but
has the same id and the same boolean ``value``.

Filtering happens in two places. The controls above the grid (group, type,
"has location" and the samples picked on the map) decide which rows the grid is
given, which is plain python and is what `filter_rows` does; the search box and
the column header filters narrow those rows in the browser. The grid reports
what is left as ``virtualRowData``, which is what the row count and the map
read.
"""

import math
from typing import Any

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import requests
from dash import dcc, html

from spectra_inspector.components.dataset_selector import (
    dataset_names,
    datasetSelectorLayoutIDs,
    dropdown_options,
    list_store_data,
)
from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import AvailableDatasets

MODE_OPTIONS = [
    {"label": "Maps", "value": False},
    {"label": "Spectra", "value": True},
]

# field, header, minimum width in pixels
_TEXT_COLUMNS = (
    ("name", "Name", 170),
    ("sample_id", "Sample", 100),
    ("group_name", "Group", 150),
    ("sample_type", "Type", 150),
    ("description", "Description", 170),
)
# field, header, minimum width in pixels, digits shown
_NUMBER_COLUMNS = (
    ("elevation", "Elevation (m)", 125, 0),
    ("lat", "Lat", 105, 5),
    ("lon", "Lon", 105, 5),
)


def _number_formatter(digits: int) -> dict[str, str]:
    return {
        "function": f"params.value == null ? '' : params.value.toFixed({digits})",
    }


COLUMN_DEFS: list[dict[str, Any]] = [
    *(
        {
            "field": field,
            "headerName": header,
            "filter": "agTextColumnFilter",
            "tooltipField": field,
            "minWidth": width,
            # the one column that says which row this is stays in view
            "pinned": "left" if field == "name" else None,
        }
        for field, header, width in _TEXT_COLUMNS
    ),
    *(
        {
            "field": field,
            "headerName": header,
            "filter": "agNumberColumnFilter",
            "valueFormatter": _number_formatter(digits),
            "type": "rightAligned",
            "minWidth": width,
        }
        for field, header, width, digits in _NUMBER_COLUMNS
    ),
]


class datasetTableLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "grid",
        "search",
        "groups",
        "types",
        "located",
        "samplefilter",
        "sampledisplay",
        "samplebadge",
        "clearsamples",
        "count",
    )

    def __init__(
        self, id_type_base: str = "dataset-table", index: int | None = None
    ) -> None:
        super().__init__(id_type_base, index)

    @property
    def grid(self) -> str:
        return self.full_id("-grid")

    @property
    def search(self) -> str:
        return self.full_id("-search")

    @property
    def groups(self) -> str:
        return self.full_id("-groups")

    @property
    def types(self) -> str:
        return self.full_id("-types")

    @property
    def located(self) -> str:
        return self.full_id("-located")

    @property
    def samplefilter(self) -> str:
        return self.full_id("-samplefilter")

    @property
    def sampledisplay(self) -> str:
        return self.full_id("-sampledisplay")

    @property
    def samplebadge(self) -> str:
        return self.full_id("-samplebadge")

    @property
    def clearsamples(self) -> str:
        return self.full_id("-clearsamples")

    @property
    def count(self) -> str:
        return self.full_id("-count")


def _text(value: Any) -> str:
    """A sample sheet cell as text. The server stringifies an empty cell, so
    the spellings of "nothing" are blanked here."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none", "null"):
        return ""
    return text


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def table_rows(listing: dict[str, Any] | None, spectrum_only: bool) -> list[dict]:
    """One row per dataset of the listing store's contents, in the mode's
    order, carrying the sample sheet record of its sample where there is one."""
    listing = listing or {}
    meta = listing.get("sample_metadata") or {}
    map_samples = meta.get("map_samples") or {}
    records = {r.get("sample_id"): r for r in meta.get("records") or []}

    rows = []
    for name in dataset_names(listing, spectrum_only):
        sample_id = map_samples.get(name)
        record = records.get(sample_id) or {}
        rows.append(
            {
                "name": name,
                "sample_id": _text(sample_id),
                "group_name": _text(record.get("group_name")),
                "sample_type": _text(record.get("sample_type")),
                "description": _text(record.get("description")),
                "lat": _number(record.get("lat")),
                "lon": _number(record.get("lon")),
                "elevation": _number(record.get("elevation")),
            }
        )
    return rows


def has_location(row: dict) -> bool:
    return row.get("lat") is not None and row.get("lon") is not None


def facet_values(rows: list[dict], field: str) -> list[str]:
    """The distinct non-blank values of a column, for its filter dropdown."""
    return sorted({row[field] for row in rows if row.get(field)})


def filter_rows(
    rows: list[dict],
    groups: list[str] | None = None,
    types: list[str] | None = None,
    located_only: bool = False,
    samples: list[str] | None = None,
) -> list[dict]:
    """The rows passing the controls above the grid.

    A group or type that no row carries is ignored rather than matching
    nothing: the dropdowns keep their value across a change of listing, and a
    leftover from the previous one should not empty the table.
    """
    known_groups = set(facet_values(rows, "group_name"))
    known_types = set(facet_values(rows, "sample_type"))
    group_set = set(groups or []) & known_groups
    type_set = set(types or []) & known_types
    sample_set = set(samples or [])

    kept = []
    for row in rows:
        if group_set and row["group_name"] not in group_set:
            continue
        if type_set and row["sample_type"] not in type_set:
            continue
        if located_only and not has_location(row):
            continue
        if sample_set and row["sample_id"] not in sample_set:
            continue
        kept.append(row)
    return kept


def count_label(
    n_shown: int, n_total: int, truncated: bool = False, spectrum_only: bool = False
) -> str:
    """The line under the grid: how many rows survive the filters, and a note
    when the listing itself is only the first part of what is on disk."""
    kind = "spectra" if spectrum_only else "datasets"
    if n_shown == n_total:
        label = f"{n_total} {kind}"
    else:
        label = f"{n_shown} of {n_total} {kind}"
    if truncated:
        label += (
            f" (the first {n_total} found: the scan stopped at the server's "
            "dataset limit, pick a narrower directory to reach the rest)"
        )
    return label


def sample_filter_label(samples: list[str] | None) -> str:
    samples = samples or []
    if len(samples) == 1:
        return f"Map selection: {samples[0]}"
    return f"Map selection: {len(samples)} samples"


def _facet_dropdown(
    component_id: dict, placeholder: str, options: list[str]
) -> dcc.Dropdown:
    # the options are rendered with the layout rather than left to the page's
    # callback: a persisted value restored against an empty list is dropped.
    return dcc.Dropdown(
        options,
        id=component_id,
        multi=True,
        placeholder=placeholder,
        persistence=True,
        persistence_type="memory",
        # see dataset_selector: the control is white in both themes
        style={"minWidth": "9rem", "color": "#212529"},
    )


def dataset_table(
    sisi: SpectraInspectorServerInterface,
    component_index: int = 0,
) -> tuple[html.Div, AvailableDatasets | None]:
    IDS = datasetTableLayoutIDs(index=component_index)
    selector_ids = datasetSelectorLayoutIDs(index=component_index)

    try:
        datasets = sisi.get_available_datasets()
    except requests.exceptions.RequestException:
        datasets = None

    if datasets is None:
        return (
            html.Div(["Could not connect to spectra_inspector_server backend."]),
            None,
        )

    listing = list_store_data(datasets)
    rows = table_rows(listing, spectrum_only=False)

    state = html.Div(
        [
            dcc.Store(
                id=selector_ids.get_id_with_index("liststore"),
                storage_type="memory",
                data=listing,
            ),
            dcc.Store(
                id=IDS.get_id_with_index("samplefilter"),
                storage_type="memory",
                data=[],
            ),
            dcc.Dropdown(
                dropdown_options(dataset_names(listing, spectrum_only=False)),
                id=selector_ids.get_id_with_index("dropdown"),
                value=None,
            ),
        ],
        hidden=True,
    )

    toolbar = html.Div(
        [
            dbc.Input(
                id=IDS.get_id_with_index("search"),
                type="search",
                placeholder="Search…",
                persistence=True,
                persistence_type="memory",
                style={"maxWidth": "14rem"},
            ),
            dbc.RadioItems(
                id=selector_ids.get_id_with_index("spectrumonly"),
                options=MODE_OPTIONS,
                value=False,
                className="btn-group si-button-radio",
                input_class_name="btn-check",
                label_class_name="btn btn-outline-secondary",
                label_checked_class_name="active",
            ),
            _facet_dropdown(
                IDS.get_id_with_index("groups"),
                "Group",
                facet_values(rows, "group_name"),
            ),
            _facet_dropdown(
                IDS.get_id_with_index("types"),
                "Type",
                facet_values(rows, "sample_type"),
            ),
            dbc.Checkbox(
                id=IDS.get_id_with_index("located"),
                label="Has location",
                value=False,
                persistence=True,
                persistence_type="memory",
                className="mb-0",
            ),
            dbc.Button(
                html.I(className="fa fa-refresh"),
                id=selector_ids.get_id_with_index("refresh"),
                color="secondary",
                title="Refresh datasets",
                className="ms-auto",
            ),
        ],
        className="si-dataset-toolbar",
    )

    grid = dag.AgGrid(
        id=IDS.get_id_with_index("grid"),
        columnDefs=COLUMN_DEFS,
        rowData=rows,
        getRowId="params.data.name",
        defaultColDef={"sortable": True, "resizable": True},
        columnSize="responsiveSizeToFit",
        dashGridOptions={
            "rowSelection": {
                "mode": "singleRow",
                "checkboxes": False,
                "enableClickSelection": True,
            },
            "animateRows": False,
            "tooltipShowDelay": 500,
            "localeText": {"noRowsToShow": "No datasets to show."},
        },
        className="si-grid si-dataset-grid",
        style={"height": "26rem", "width": "100%"},
    )

    footer = html.Div(
        [
            html.Span(
                count_label(len(rows), len(rows), truncated=listing["truncated"]),
                id=IDS.get_id_with_index("count"),
                className="text-muted small",
            ),
            html.Span(
                [
                    dbc.Badge("", id=IDS.get_id_with_index("samplebadge"), pill=True),
                    dbc.Button(
                        "Clear",
                        id=IDS.get_id_with_index("clearsamples"),
                        color="link",
                        size="sm",
                        n_clicks=0,
                    ),
                ],
                id=IDS.get_id_with_index("sampledisplay"),
                hidden=True,
                className="ms-auto",
            ),
        ],
        className="si-dataset-footer",
    )

    layout = html.Div(
        [state, toolbar, grid, footer],
        id=IDS.get_id_with_index("div"),
        className="si-dataset-table",
    )
    return layout, datasets

"""The data selection page: the dataset table, the sample map and the metadata
of the selected dataset.

The selection is the value of the (hidden) dataset dropdown, which
`update_selected_dataset` carries into the user store; everything else on the
page is a view of it. The table and the map are linked through the grid's
``virtualRowData``, the rows left after every filter: `update_map_figure` dims
the samples that have no row left, and picking samples on the map
(`filter_table_from_map`) is one more filter on the table.
"""

import dash
import dash_bootstrap_components as dbc
from dash import (
    ClientsideFunction,
    Input,
    Output,
    Patch,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    set_props,
)

from spectra_inspector.components import (
    datasetSelectorLayoutIDs,
    directory_selector,
    directorySelectorLayoutIDs,
    sample_map,
)
from spectra_inspector.components.dataset_selector import (
    dataset_names,
    dropdown_options,
    list_store_data,
    resolve_spectrum_only,
)
from spectra_inspector.components.dataset_table import (
    count_label,
    dataset_table,
    datasetTableLayoutIDs,
    facet_values,
    filter_rows,
    sample_filter_label,
    table_rows,
)
from spectra_inspector.components.nested_accordian import nested_accordian
from spectra_inspector.logging import spectraLogger
from spectra_inspector.user_store_model import (
    USER_STORE_DIV_ID,
    UserStore,
    updateDataStore,
)
from spectra_inspector.utilities.export_metadata import (
    sample_metadata_display_dict,
    sample_record,
)
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import AvailableDatasets
from spectra_inspector.utilities.sample_url import sample_name_to_url

dash.register_page(__name__, path="/", order=0)

_basemapIDs = sample_map.sampleMapLayoutIDs()


selectorIDs = datasetSelectorLayoutIDs(index=0)
tableIDs = datasetTableLayoutIDs(index=0)
dirSelectorIDs = directorySelectorLayoutIDs(index=0)

OPEN_LOCATION_ID = "dataset-open-location"

_MAP_ID = {"type": _basemapIDs.samplemap, "index": 0}
_MAP_STYLE_ID = {"type": _basemapIDs.dropdown, "index": 0}
_DROPDOWN_ID = selectorIDs.get_id_with_index("dropdown")
_LISTSTORE_ID = selectorIDs.get_id_with_index("liststore")
_MODE_ID = selectorIDs.get_id_with_index("spectrumonly")
_GRID_ID = tableIDs.get_id_with_index("grid")
_SAMPLEFILTER_ID = tableIDs.get_id_with_index("samplefilter")

# the id types of the controls that filter the table's rows
_FILTER_TYPES = frozenset(
    {tableIDs.groups, tableIDs.types, tableIDs.located, tableIDs.samplefilter}
)


def inspector_href(dataset: str | None, spectrum_only: bool) -> str:
    """The inspector's URL for a dataset. The inspector renders its own
    selector from the URL, so the mode rides along: the user store is not
    readable at layout time."""
    url_sample = sample_name_to_url(dataset) if dataset else "none"
    href = f"/inspector/{url_sample}"
    if spectrum_only:
        href += "?spectrum_only=true"
    return href


def active_dataset_display(dataset: str | None, spectrum_only: bool) -> list:
    """What the page header says about the selection, with the way into the
    inspector next to it."""
    if not dataset:
        return [html.Span("No dataset selected.", className="text-muted")]
    return [
        html.Span("Active:", className="fw-bold"),
        dbc.Badge(
            dataset,
            color="warning",
            className="fs-6",
            # the themes' own "dark" text colours are too faint on the badge
            style={"color": "#212529"},
        ),
        dbc.NavLink(
            dbc.Button(
                ["Open in inspector ", html.I(className="fa fa-arrow-right")],
                color="primary",
                size="sm",
            ),
            href=inspector_href(dataset, spectrum_only),
            className="p-0",
        ),
    ]


def sample_summary(dataset: str, sample_metadata: dict | None) -> html.Div:
    """One line of what the sample sheet says about a dataset's sample, with
    the description underneath."""
    record = sample_record(sample_metadata, dataset) or {}
    rows = table_rows(
        {
            "available_files": [dataset],
            "sample_metadata": {
                "records": [record] if record else [],
                "map_samples": (sample_metadata or {}).get("map_samples"),
            },
        },
        spectrum_only=False,
    )
    row = rows[0]

    parts = [dataset]
    if row["sample_id"] and row["sample_id"] != dataset:
        parts.append(f"sample {row['sample_id']}")
    if row["group_name"]:
        parts.append(f"group {row['group_name']}")
    if row["sample_type"]:
        parts.append(row["sample_type"])
    if row["lat"] is not None and row["lon"] is not None:
        parts.append(f"{row['lat']:.5f}, {row['lon']:.5f}")
    if row["elevation"] is not None:
        parts.append(f"{row['elevation']:.0f} m")

    children = [html.Div(" · ".join(parts), className="fw-bold")]
    if row["description"]:
        children.append(html.Div(row["description"], className="text-muted"))
    return html.Div(children, className="mb-2")


def layout(**kwargs) -> html.Div:  # noqa: ARG001

    sisi = SpectraInspectorServerInterface()
    _dataset_table, available_data = dataset_table(sisi)

    base_map, _ = sample_map.get_layout(available_data=available_data)

    header = html.Div(
        [
            html.H1("Data selection", className="mb-0 me-auto"),
            html.Div(
                active_dataset_display(None, spectrum_only=False),
                id="nav-link-loader-div",
                className="si-active-dataset",
            ),
        ],
        className="si-active-dataset mb-3",
    )

    _layout = html.Div(
        [
            dcc.Location(id=OPEN_LOCATION_ID, refresh="callback-nav"),
            header,
            directory_selector(component_index=0),
            dbc.Row(
                [
                    dbc.Col(dbc.Card(dbc.CardBody(_dataset_table)), xs=12, xl=8),
                    dbc.Col(dbc.Card(dbc.CardBody(base_map)), xs=12, xl=4),
                ],
                className="g-3 mt-0",
            ),
            html.Div(id="metadata-display", className="mt-3"),
        ]
    )
    return _layout


@callback(
    Output("nav-link-loader-div", "children"),
    Output("metadata-display", "children"),
    Output(USER_STORE_DIV_ID, "data"),
    Input(_DROPDOWN_ID, "value"),
    State(USER_STORE_DIV_ID, "data"),
    State(_LISTSTORE_ID, "data"),
    State(_MODE_ID, "value"),
    prevent_initial_call=True,
)
def update_selected_dataset(
    input_value: str | None,
    current_user_data: dict,
    listing: dict | None,
    spectrum_only_switch: bool | None = False,
):
    """Carry the selection into the user store and show its metadata.

    This must not write the listing store: the table's rows, and through them
    the selection, are derived from that store, so an edge from the selection
    back to it would close a dependency cycle. `refresh_listing` does that.
    """
    sisi = SpectraInspectorServerInterface()

    current_user_data = current_user_data or {}
    dir_sync = UserStore(**current_user_data).directory_sync()
    spectrum_only = resolve_spectrum_only(current_user_data, spectrum_only_switch)

    has_input = input_value and input_value != "none"

    new_user_data = updateDataStore(current_user_data, "selected_dataset", input_value)
    new_user_data = updateDataStore(new_user_data, "spectrum_only", spectrum_only)
    if listing is not None:
        # the sample sheet records of the listing the selection was made from
        new_user_data = updateDataStore(
            new_user_data, "sample_metadata", listing.get("sample_metadata")
        )

    meta_json_str: str = "{}"
    if has_input:
        meta = sisi.get_combined_image_metadata(
            input_value, directory_sync=dir_sync, spectrum_only=spectrum_only
        )
        meta_json_str = meta.model_dump_json()
        sample_metadata = new_user_data.get("sample_metadata")
        # the same dict the summary export writes out
        meta_dict = sample_metadata_display_dict(meta, sample_metadata, input_value)
        md = dbc.Card(
            dbc.CardBody(
                [
                    sample_summary(input_value, sample_metadata),
                    nested_accordian(meta_dict),
                ]
            )
        )
    else:
        md = html.Div()
    new_user_data = updateDataStore(new_user_data, "metadata_json", meta_json_str)

    active = active_dataset_display(input_value if has_input else None, spectrum_only)

    return active, md, new_user_data


@callback(
    Output(_LISTSTORE_ID, "data", allow_duplicate=True),
    Output(_DROPDOWN_ID, "options"),
    Output(_DROPDOWN_ID, "value"),
    Output(USER_STORE_DIV_ID, "data", allow_duplicate=True),
    Input(selectorIDs.get_id_with_index("refresh"), "n_clicks"),
    State(USER_STORE_DIV_ID, "data"),
    State(_MODE_ID, "value"),
    prevent_initial_call=True,
)
def refresh_listing(
    n_clicks: int | None,
    current_user_data: dict | None,
    spectrum_only_switch: bool | None = False,
):
    """Ask the server to rescan, and start over from the new listing.

    The selection is cleared with it, which chains `update_selected_dataset`
    after this callback whenever there was one, so that it reads the user
    store written here rather than a snapshot from before.
    """
    if not n_clicks:
        return no_update, no_update, no_update, no_update

    current_user_data = current_user_data or {}
    dir_sync = UserStore(**current_user_data).directory_sync()
    spectrum_only = resolve_spectrum_only(current_user_data, spectrum_only_switch)

    sisi = SpectraInspectorServerInterface()
    available = sisi.get_available_datasets(refresh_db=True, directory_sync=dir_sync)
    listing = list_store_data(available)

    new_user_data = updateDataStore(
        current_user_data, "sample_metadata", listing["sample_metadata"]
    )
    new_user_data = updateDataStore(new_user_data, "selected_dataset", "none")
    new_user_data = updateDataStore(new_user_data, "metadata_json", "")

    options = dropdown_options(dataset_names(listing, spectrum_only))
    return listing, options, None, new_user_data


@callback(
    Output(_DROPDOWN_ID, "options", allow_duplicate=True),
    Output(_DROPDOWN_ID, "value", allow_duplicate=True),
    Input(_LISTSTORE_ID, "id"),
    State(_LISTSTORE_ID, "data"),
    State(USER_STORE_DIV_ID, "data"),
    prevent_initial_call="initial_duplicate",
)
def hydrate_selection(_store_id: dict, listing: dict | None, user_data: dict | None):
    """Show a freshly mounted page the dataset the session already has active.

    Pages are rebuilt on every navigation and the layout cannot read the user
    store, so coming back from the inspector would otherwise show nothing
    selected. The options go out together with the value because the layout
    renders the map list: a spectrum's name set against it would be dropped by
    the dropdown, and `update_selected_dataset` would then clear the store.
    """
    store = UserStore(**(user_data or {}))
    selected = store.selected_dataset
    names = dataset_names(listing or {}, store.spectrum_only)
    if not selected or selected == "none" or selected not in names:
        return no_update, no_update
    return dropdown_options(names), selected


@callback(
    Output(_GRID_ID, "rowData"),
    Output(_GRID_ID, "selectedRows", allow_duplicate=True),
    Output(tableIDs.get_id_with_index("groups"), "options"),
    Output(tableIDs.get_id_with_index("types"), "options"),
    Output(tableIDs.get_id_with_index("sampledisplay"), "hidden"),
    Output(tableIDs.get_id_with_index("samplebadge"), "children"),
    Input(_LISTSTORE_ID, "data"),
    Input(_MODE_ID, "value"),
    Input(tableIDs.get_id_with_index("groups"), "value"),
    Input(tableIDs.get_id_with_index("types"), "value"),
    Input(tableIDs.get_id_with_index("located"), "value"),
    Input(_SAMPLEFILTER_ID, "data"),
    State(_DROPDOWN_ID, "value"),
    prevent_initial_call="initial_duplicate",
)
def update_table_rows(
    listing: dict | None,
    spectrum_only: bool | None,
    groups: list[str] | None,
    types: list[str] | None,
    located_only: bool | None,
    samples: list[str] | None,
    selected: str | None,
):
    """Give the grid the rows that pass the controls above it.

    The grid drops its selection when the selected row is filtered out, and
    does not take it back when the row returns, so a change of filter sets the
    selection again if the selected dataset is among the rows. Only a change
    of filter: a new listing or mode clears the selection in a callback of its
    own, and the value read here may be the one from before that.
    """
    rows = table_rows(listing, bool(spectrum_only))
    shown = filter_rows(
        rows,
        groups=groups,
        types=types,
        located_only=bool(located_only),
        samples=samples,
    )
    selected_rows = no_update
    triggered = {
        component_id["type"]
        for component_id in ctx.triggered_prop_ids.values()
        if isinstance(component_id, dict)
    }
    filter_changed = bool(triggered) and triggered <= _FILTER_TYPES
    if filter_changed and any(row["name"] == selected for row in shown):
        selected_rows = {"ids": [selected]}
    return (
        shown,
        selected_rows,
        facet_values(rows, "group_name"),
        facet_values(rows, "sample_type"),
        not samples,
        sample_filter_label(samples),
    )


def selected_row_name(selected_rows: list[dict] | dict | None) -> str | None:
    """The dataset a grid's ``selectedRows`` names. The prop is a list of rows
    when the grid reports a selection, and still the ``{"ids": [...]}`` a
    callback set it to until the grid has done so."""
    if not selected_rows:
        return None
    if isinstance(selected_rows, dict):
        ids = selected_rows.get("ids") or []
        return ids[0] if ids else None
    return selected_rows[0].get("name")


@callback(
    Output(_DROPDOWN_ID, "value", allow_duplicate=True),
    Output(_GRID_ID, "selectedRows", allow_duplicate=True),
    Input(_GRID_ID, "selectedRows"),
    Input(_DROPDOWN_ID, "value"),
    prevent_initial_call=True,
)
def sync_table_selection(selected_rows: list[dict] | dict | None, value: str | None):
    """Keep the grid's selected row and the dataset dropdown in step.

    A row picked in the grid becomes the dropdown's value. The other way
    round, whatever else sets or clears the dropdown (a new working directory,
    the mode control, a refresh, a click on the map) moves the grid's
    selection. An emptied grid selection is not carried over: it is what the
    grid reports when a filter hides the selected row, and that should not
    deselect the dataset.
    """
    has_value = bool(value) and value != "none"
    grid_name = selected_row_name(selected_rows)

    if ctx.triggered_id == _GRID_ID:
        if not grid_name or grid_name == value:
            return no_update, no_update
        return grid_name, no_update

    if has_value:
        if grid_name == value:
            return no_update, no_update
        return no_update, {"ids": [value]}
    if grid_name is None:
        return no_update, no_update
    return no_update, []


@callback(
    Output(OPEN_LOCATION_ID, "href"),
    Input(_GRID_ID, "cellDoubleClicked"),
    State(_MODE_ID, "value"),
    State(USER_STORE_DIV_ID, "data"),
    prevent_initial_call=True,
)
def open_double_clicked_dataset(
    cell: dict | None, mode: bool | None, user_data: dict | None
):
    """A double click on a row opens it in the inspector."""
    name = (cell or {}).get("rowId")
    if not name:
        return no_update
    return inspector_href(name, resolve_spectrum_only(user_data, mode))


clientside_callback(
    ClientsideFunction(namespace="dataset_table", function_name="quick_filter"),
    Output(_GRID_ID, "dashGridOptions"),
    Input(tableIDs.get_id_with_index("search"), "value"),
    State(_GRID_ID, "dashGridOptions"),
)


@callback(
    Output(tableIDs.get_id_with_index("count"), "children"),
    Input(_GRID_ID, "virtualRowData"),
    Input(_LISTSTORE_ID, "data"),
    Input(_MODE_ID, "value"),
    prevent_initial_call=True,
)
def update_table_count(
    virtual_rows: list[dict] | None,
    listing: dict | None,
    spectrum_only: bool | None,
):
    n_total = len(dataset_names(listing or {}, bool(spectrum_only)))
    n_shown = n_total if virtual_rows is None else len(virtual_rows)
    return count_label(
        min(n_shown, n_total),
        n_total,
        truncated=bool((listing or {}).get("truncated")),
        spectrum_only=bool(spectrum_only),
    )


def _listing_metadata(listing: dict | None) -> dict:
    return (listing or {}).get("sample_metadata") or {}


def _visible_samples(virtual_rows: list[dict] | None) -> set[str] | None:
    if virtual_rows is None:
        return None
    return {row["sample_id"] for row in virtual_rows if row.get("sample_id")}


@callback(
    Output(_MAP_ID, "figure"),
    Input(_LISTSTORE_ID, "data"),
    Input(_MAP_STYLE_ID, "value"),
    Input(_GRID_ID, "virtualRowData"),
    Input(_DROPDOWN_ID, "value"),
    State(_SAMPLEFILTER_ID, "data"),
    prevent_initial_call=True,
)
def update_map_figure(
    listing: dict | None,
    map_style: str | None,
    virtual_rows: list[dict] | None,
    selected: str | None,
    sample_filter: list[str] | None,
):
    """The one writer of the map figure.

    A new listing (another working directory, a refresh) means other samples,
    so the figure is rebuilt; everything else is a `Patch`: the map style, the
    samples dimmed because the table has no row left for them, and the disc
    under the active dataset's sample, on which the map is centered when the
    selection is what changed. Doing all of it in one callback keeps a patch
    from racing the rebuild it belongs to.
    """
    meta = _listing_metadata(listing)
    records = meta.get("records") or []
    active_sample = (meta.get("map_samples") or {}).get(selected) if selected else None
    styling = sample_map.point_styling(
        records, _visible_samples(virtual_rows), active_sample
    )
    style = sample_map._map_styles.get(map_style or "Satellite", "satellite")

    if ctx.triggered_id == _LISTSTORE_ID:
        available = AvailableDatasets(
            available_files=(listing or {}).get("available_files") or [],
            sample_metadata=meta or None,
        )
        try:
            fig = sample_map.get_map(style, available_data=available)
        except (RuntimeError, KeyError, ValueError):
            spectraLogger.exception("Failed to rebuild the sample map")
            return no_update
        return sample_map.apply_point_styling(fig, styling, recenter=True)

    patch = Patch()
    patch["layout"]["map"]["style"] = style
    if not sample_filter:
        # drop the outline a box or lasso selection leaves behind once the
        # filter it stood for is gone
        patch["layout"]["selections"] = []
    return sample_map.apply_point_styling(
        patch, styling, recenter=ctx.triggered_id == _DROPDOWN_ID
    )


@callback(
    Output(_SAMPLEFILTER_ID, "data"),
    Output(_DROPDOWN_ID, "value", allow_duplicate=True),
    Input(_MAP_ID, "selectedData"),
    Input(_MAP_ID, "clickData"),
    Input(tableIDs.get_id_with_index("clearsamples"), "n_clicks"),
    Input(_LISTSTORE_ID, "data"),
    State(_SAMPLEFILTER_ID, "data"),
    State(_MODE_ID, "value"),
    State(_DROPDOWN_ID, "value"),
    prevent_initial_call=True,
)
def filter_table_from_map(
    selected_data: dict | None,
    click_data: dict | None,
    _n_clear: int | None,
    listing: dict | None,
    current: list[str] | None,
    spectrum_only: bool | None,
    current_value: str | None,
):
    """Samples picked on the map filter the table.

    A box or lasso selection filters to the samples inside it, a click to the
    one sample clicked; emptying the selection on the map, the "Clear" button
    and a new listing all lift the filter. A click on a sample with exactly one
    dataset also selects that dataset, since there is nothing left to choose.

    Dash only fires on a changed prop and clicking the same point twice yields
    the same `clickData`, so it is cleared once read (a side update, which does
    not re-trigger anything).
    """
    current = current or []
    known = {str(r["sample_id"]) for r in _listing_metadata(listing).get("records", [])}
    trigger_props = {t["prop_id"].rpartition(".")[2] for t in ctx.triggered}

    samples: list[str] = []
    select: str | None = None
    if "clickData" in trigger_props and click_data:
        set_props(_MAP_ID, {"clickData": None})
        samples = [
            s for s in sample_map.sample_ids_from_points(click_data) if s in known
        ]
        if not samples:
            return no_update, no_update
        rows = filter_rows(table_rows(listing, bool(spectrum_only)), samples=samples)
        if len(rows) == 1:
            select = rows[0]["name"]
    elif "selectedData" in trigger_props:
        picked = sample_map.sample_ids_from_points(selected_data)
        samples = [s for s in picked if s in known]
    elif not ({"n_clicks", "data"} & trigger_props):
        return no_update, no_update

    new_filter = no_update if samples == current else samples
    new_value = no_update if select in (None, current_value) else select
    return new_filter, new_value

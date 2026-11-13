"""A picker for the server-side working directory.

Desktop deployments point the server at a data root holding far more datasets
than a dataset list can usefully show, and scanning all of it at startup is
slow. In desktop mode the server defers that scan and instead lets a client walk
the tree (always within the data root) and pick one directory to scan.

The page shows one line, the directory in use and what was loaded from it,
with a button that opens the picker as a dialog laid out like a file explorer:
a breadcrumb of the position, the subdirectories of that position in a grid,
and "Use" to commit. Browsing never walks a subtree: every position costs the
server one listing of one directory, and the count shown is of that directory
alone. Only committing scans, and only then does "Include subdirectories" mean
anything -- it says whether that scan is recursive.

"Use" commits the subdirectory selected in the grid, or the directory being
browsed when none is, and its label says which. A double click (or Enter, see
``assets/dataset_table.js``) descends instead.

Two stores hold the state: the browse position, which only the dialog shows,
and the committed directory, whose payload `store_working_directory` copies
into the user store. The line on the page is rendered from the user store, so
it never shows a position that was merely browsed.

The directories committed lately are kept in the browser's local storage and
listed in the dialog, a click away however deep they are. The list is the
browser's own: it outlives the session, and nothing about it is on the server.
"""

from typing import Any

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import (
    ALL,
    MATCH,
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)

from spectra_inspector.components.dataset_selector import (
    dataset_names,
    datasetSelectorLayoutIDs,
    dropdown_options,
    list_store_data,
)
from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.logging import spectraLogger
from spectra_inspector.settings import Settings
from spectra_inspector.user_store_model import (
    USER_STORE_DIV_ID,
    UserStore,
    sample_metadata_for_store,
    updateDataStore,
)
from spectra_inspector.utilities.interface import (
    ServerRequestError,
    SpectraInspectorServerInterface,
)

DATA_ROOT_LABEL = "<data root>"


class directorySelectorLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "current",
        "loaded",
        "open",
        "modal",
        "cancel",
        "path",
        "crumb",
        "filter",
        "entries",
        "count",
        "use",
        "recursive",
        "status",
        "browsestore",
        "committedstore",
        "rootstore",
        "recent",
        "recententry",
    )

    def __init__(
        self, id_type_base: str = "directory-selector", index: int | None = None
    ) -> None:
        super().__init__(id_type_base, index)

    @property
    def current(self) -> str:
        return self.full_id("-current")

    @property
    def loaded(self) -> str:
        return self.full_id("-loaded")

    @property
    def open(self) -> str:
        return self.full_id("-open")

    @property
    def modal(self) -> str:
        return self.full_id("-modal")

    @property
    def cancel(self) -> str:
        return self.full_id("-cancel")

    @property
    def path(self) -> str:
        return self.full_id("-path")

    @property
    def crumb(self) -> str:
        return self.full_id("-crumb")

    @property
    def filter(self) -> str:
        return self.full_id("-filter")

    @property
    def entries(self) -> str:
        return self.full_id("-entries")

    @property
    def count(self) -> str:
        return self.full_id("-count")

    @property
    def use(self) -> str:
        return self.full_id("-use")

    @property
    def recursive(self) -> str:
        return self.full_id("-recursive")

    @property
    def status(self) -> str:
        return self.full_id("-status")

    @property
    def browsestore(self) -> str:
        return self.full_id("-browsestore")

    @property
    def committedstore(self) -> str:
        return self.full_id("-committedstore")

    @property
    def rootstore(self) -> str:
        return self.full_id("-rootstore")

    @property
    def recent(self) -> str:
        return self.full_id("-recent")

    @property
    def recententry(self) -> str:
        return self.full_id("-recententry")


# One list for both pages' pickers, so it has a plain id rather than an
# indexed one: a store in local storage is keyed by its id.
RECENT_STORE_ID = "directory-selector-recentstore"
MAX_RECENT_DIRECTORIES = 8

USE_CURRENT_LABEL = "Use this directory"
NO_DIRECTORY_LABEL = "none chosen yet"


def desktop_mode_enabled() -> bool:
    return Settings().desktop_mode


def data_root_label(sisi: SpectraInspectorServerInterface | None = None) -> str:
    """What to call the top of the browsable tree.

    A desktop deployment points at a data root the user chose themselves, so
    spelling it out is more useful than a placeholder -- and it is the only way
    to tell which root a relative path is relative to. Elsewhere the data root
    is a server-side detail, so the placeholder stands in for it.
    """
    if not desktop_mode_enabled():
        return DATA_ROOT_LABEL

    if sisi is None:
        sisi = SpectraInspectorServerInterface()

    try:
        info = sisi.get_info()
    except ServerRequestError as err:
        spectraLogger.warning(f"Could not fetch the server data root: {err}")
        return DATA_ROOT_LABEL

    return info.spectra_inspector_data_root or DATA_ROOT_LABEL


def path_label(path: str | None, root: str | None = None) -> str:
    """Human readable form of a path relative to the server data root."""
    root_label = root or DATA_ROOT_LABEL
    if not path:
        return root_label
    return f"{root_label.rstrip('/')}/{path}"


def directory_selector(
    component_index: int = 0,
    enabled: bool | None = None,
) -> html.Div:
    """The working-directory line and the dialog it opens.

    Returns an empty div outside of desktop mode, which leaves every callback
    below inert: none of their inputs exist on the page.
    """

    IDS = directorySelectorLayoutIDs(index=component_index)

    if enabled is None:
        enabled = desktop_mode_enabled()

    if not enabled:
        return html.Div(id=IDS.full_id(f"-disabled-{component_index}"))

    root = data_root_label()

    stores = [
        # None rather than a path: it means "not hydrated yet", and
        # `hydrate_browse_position` fills it in on mount from the user
        # store. Both pages embed a picker of their own and dash rebuilds a
        # page's layout on every navigation, so a hardcoded path here is
        # what used to reset the picker to the data root on a page switch.
        dcc.Store(
            id=IDS.get_id_with_index("browsestore"),
            storage_type="memory",
            data=None,
        ),
        dcc.Store(
            id=IDS.get_id_with_index("committedstore"),
            storage_type="memory",
            data={},
        ),
        dcc.Store(
            id=IDS.get_id_with_index("rootstore"),
            storage_type="memory",
            data=root,
        ),
        dcc.Store(id=RECENT_STORE_ID, storage_type="local", data=[]),
    ]

    summary = html.Div(
        [
            html.Span("Working directory:", className="fw-bold"),
            html.Span(
                NO_DIRECTORY_LABEL,
                id=IDS.get_id_with_index("current"),
                style={"wordBreak": "break-all"},
            ),
            dbc.Button(
                "Change…",
                id=IDS.get_id_with_index("open"),
                n_clicks=0,
                color="secondary",
                size="sm",
            ),
            html.Span(id=IDS.get_id_with_index("loaded"), className="text-muted small"),
        ],
        className="si-working-directory",
    )

    # a directory can hold a great many subdirectories; the grid only renders
    # the rows in view, and its quick filter narrows them without a round trip.
    entries = dag.AgGrid(
        id=IDS.get_id_with_index("entries"),
        columnDefs=[{"field": "name", "headerName": "Subdirectories"}],
        rowData=[],
        getRowId="params.data.path",
        defaultColDef={"sortable": True, "flex": 1},
        dashGridOptions={
            "rowSelection": {
                "mode": "singleRow",
                "checkboxes": False,
                "enableClickSelection": True,
            },
            "animateRows": False,
            "localeText": {"noRowsToShow": "No subdirectories."},
        },
        className="si-grid si-directory-grid",
        style={"height": "20rem", "width": "100%"},
    )

    dialog = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Choose working directory")),
            dbc.ModalBody(
                [
                    html.Div(
                        [
                            html.Div(
                                breadcrumb("", root, component_index),
                                id=IDS.get_id_with_index("path"),
                                className="si-directory-path",
                            ),
                            dbc.Input(
                                id=IDS.get_id_with_index("filter"),
                                type="search",
                                placeholder="Filter…",
                                size="sm",
                                style={"maxWidth": "12rem"},
                            ),
                        ],
                        className="si-directory-bar",
                    ),
                    html.Div(
                        [
                            html.Div(
                                recent_directories([], component_index),
                                id=IDS.get_id_with_index("recent"),
                                className="si-directory-recent",
                            ),
                            html.Div(entries, className="si-directory-entries"),
                        ],
                        className="si-directory-body",
                    ),
                    html.Div(
                        id=IDS.get_id_with_index("count"),
                        className="text-muted small mt-2",
                    ),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Checkbox(
                        id=IDS.get_id_with_index("recursive"),
                        label="Include subdirectories when loading",
                        value=True,
                        className="me-auto mb-0",
                    ),
                    dcc.Loading(
                        html.Div(
                            id=IDS.get_id_with_index("status"),
                            className="text-danger small",
                        ),
                        type="circle",
                    ),
                    dbc.Button(
                        "Cancel",
                        id=IDS.get_id_with_index("cancel"),
                        n_clicks=0,
                        color="secondary",
                    ),
                    dbc.Button(
                        USE_CURRENT_LABEL,
                        id=IDS.get_id_with_index("use"),
                        n_clicks=0,
                        color="primary",
                    ),
                ]
            ),
        ],
        id=IDS.get_id_with_index("modal"),
        is_open=False,
        size="lg",
        centered=True,
    )

    return html.Div(
        [*stores, summary, dialog],
        id=IDS.get_id_with_index("div"),
    )


_IDS = directorySelectorLayoutIDs()
_datasetIDS = datasetSelectorLayoutIDs()


def _matched_index() -> int:
    """The component index this MATCH callback fired for.

    Taken from the outputs rather than the trigger, so it is also right on the
    initial call, when there is no trigger. The picker is index 0 on the data
    selection page and index 1 on the inspector.
    """
    try:
        return ctx.outputs_list[0]["id"]["index"]
    except (AttributeError, IndexError, KeyError, TypeError):
        return 0


def crumb_id(component_index: int, path: str) -> dict[str, Any]:
    """The id of one clickable breadcrumb segment.

    The extra `name` key carries the path, so the navigation callback can read
    it straight off ctx.triggered_id. It is an ALL wildcard there, which is
    allowed alongside the MATCH on `index`.
    """
    return {"type": _IDS.crumb, "index": component_index, "name": path}


def breadcrumb(path: str | None, root: str, component_index: int) -> list:
    """The browse position as segments, each but the last a link to it.

    The first segment is the data root, spelled out as `data_root_label` has
    it; the last is the position itself, so it is plain text.
    """
    segments = [(root, "")]
    walked = ""
    for part in (path or "").split("/"):
        if not part:
            continue
        walked = f"{walked}/{part}" if walked else part
        segments.append((part, walked))

    children: list = []
    for i, (label, target) in enumerate(segments):
        if i:
            children.append(html.Span("/", className="text-muted"))
        if i == len(segments) - 1:
            children.append(html.Span(label, className="fw-bold"))
        else:
            children.append(
                dbc.Button(
                    label,
                    id=crumb_id(component_index, target),
                    n_clicks=0,
                    color="link",
                    size="sm",
                    className="p-0 text-start",
                )
            )
    return children


def recent_id(component_index: int, path: str) -> dict[str, Any]:
    """The id of one recent directory, carrying its path like `crumb_id`."""
    return {"type": _IDS.recententry, "index": component_index, "name": path}


def remember_directory(recent: list[str] | None, path: str | None) -> list[str]:
    """The recent list with ``path`` moved to the front. The data root is left
    out: it is always one click away on the breadcrumb."""
    kept = [path] if path else []
    for known in recent or []:
        if isinstance(known, str) and known and known not in kept:
            kept.append(known)
    return kept[:MAX_RECENT_DIRECTORIES]


def recent_directories(recent: list[str] | None, component_index: int) -> list:
    """The dialog's list of recent directories, each a link to browse it."""
    paths = remember_directory(recent, None)
    heading = html.Div("Recent", className="fw-bold small mb-1")
    if not paths:
        return [heading, html.Div("None yet.", className="text-muted small")]
    return [
        heading,
        dbc.ListGroup(
            [
                dbc.ListGroupItem(
                    path,
                    id=recent_id(component_index, path),
                    action=True,
                    n_clicks=0,
                    className="small px-2 py-1",
                )
                for path in paths
            ],
            flush=True,
        ),
    ]


def _entry_rows(listing) -> list[dict[str, str]]:
    return [{"name": d.name, "path": d.path} for d in listing.directories]


@callback(
    Output({"type": _IDS.browsestore, "index": MATCH}, "data"),
    Input({"type": _IDS.entries, "index": MATCH}, "cellDoubleClicked"),
    Input({"type": _IDS.crumb, "index": MATCH, "name": ALL}, "n_clicks"),
    Input({"type": _IDS.recententry, "index": MATCH, "name": ALL}, "n_clicks"),
    Input({"type": _IDS.committedstore, "index": MATCH}, "data"),
    State({"type": _IDS.browsestore, "index": MATCH}, "data"),
    prevent_initial_call=True,
)
def navigate_directory(
    double_clicked: dict | None,
    crumb_clicks: list[int | None],
    recent_clicks: list[int | None],
    committed: dict | None,
    browse_data: dict | None,
):
    """Move the browse position: down into a double-clicked subdirectory, up to
    a breadcrumb segment, across to a recent directory, or onto a directory
    that was just committed (which may be a subdirectory picked in the grid
    rather than the position)."""

    triggered = ctx.triggered_id or {}
    current = (browse_data or {}).get("path", "")

    if triggered.get("type") == _IDS.entries:
        path = (double_clicked or {}).get("rowId")
        if not path:
            return no_update
        return {"path": path}

    if triggered.get("type") in (_IDS.crumb, _IDS.recententry):
        clicks = crumb_clicks if triggered["type"] == _IDS.crumb else recent_clicks
        if not any(clicks or []):
            # the links were just re-rendered, which fires this with every
            # count at 0
            return no_update
        return {"path": triggered.get("name", "")}

    if triggered.get("type") == _IDS.committedstore:
        if not committed or committed.get("path", "") == current:
            return no_update
        return {"path": committed.get("path", "")}

    return no_update


@callback(
    Output({"type": _IDS.browsestore, "index": MATCH}, "data", allow_duplicate=True),
    Input({"type": _IDS.div, "index": MATCH}, "id"),
    State(USER_STORE_DIV_ID, "data"),
    prevent_initial_call="initial_duplicate",
)
def hydrate_browse_position(_div_id: dict, user_data: dict | None):
    """Open a freshly mounted picker on the directory already in use.

    The trigger is the wrapping div's own (static) id, which is just a way of
    getting a MATCH-keyed callback to fire once per mount. Writing the browse
    store from here needs `allow_duplicate` because `navigate_directory` writes
    it too, and `prevent_initial_call="initial_duplicate"` is the one spelling
    that permits that *and* still fires on mount -- a bare `allow_duplicate`
    requires `prevent_initial_call=True`, which is exactly what must not happen.
    """

    return {"path": (user_data or {}).get("working_directory") or ""}


def _count_label(n: int, spectrum_only: bool = False) -> str:
    if spectrum_only:
        return f"{n} spectrum" if n == 1 else f"{n} spectra"
    return f"{n} dataset" if n == 1 else f"{n} datasets"


def loaded_status(
    n_datasets: int, truncated: bool = False, spectrum_only: bool = False
) -> html.Span:
    """What the page says was loaded from the directory in use.

    A truncated scan is called out explicitly: the server stopped at its
    SPECTRA_INSPECTOR_MAX_DATASETS limit, so the listing holds the first N of
    an unknown larger number and the missing ones are only reachable by picking
    a narrower directory.
    """

    counted = _count_label(n_datasets, spectrum_only)

    if not truncated:
        return html.Span(f"{counted} loaded.")

    return html.Span(
        f"Showing the first {counted}: the server stopped scanning at its "
        "dataset limit, so this directory holds more than are listed. Pick a "
        "subdirectory to reach the rest.",
        className="text-warning",
    )


def browse_status(n_datasets: int, n_spectra: int) -> str:
    """What the dialog says about the directory being browsed. The counts are
    of this directory alone, and say so: the subdirectories are not walked
    until a directory is committed."""
    return (
        f"This directory: {_count_label(n_datasets)}, "
        f"{_count_label(n_spectra, spectrum_only=True)}."
    )


def committed_status(user_data: dict | None) -> html.Span | None:
    """`loaded_status` for the directory in use, or None before one is chosen.

    Built from the user store rather than remembered per mount: the line is
    page-local, and both pages show one. The store holds what was found in the
    working directory, counted here as spectra or datasets by its mode.
    """

    store = UserStore(**(user_data or {}))
    if store.working_directory is None or store.available_files is None:
        return None
    if store.spectrum_only:
        n_loaded = len(store.available_spectra or [])
    else:
        n_loaded = len(store.available_files)
    return loaded_status(
        n_loaded,
        truncated=store.truncated,
        spectrum_only=store.spectrum_only,
    )


@callback(
    Output({"type": _IDS.path, "index": MATCH}, "children"),
    Output({"type": _IDS.entries, "index": MATCH}, "rowData"),
    Output({"type": _IDS.entries, "index": MATCH}, "selectedRows"),
    Output({"type": _IDS.count, "index": MATCH}, "children"),
    Input({"type": _IDS.browsestore, "index": MATCH}, "data"),
)
def show_directory_listing(browse_data: dict | None):
    """Fetch the listing for the current browse position and render it: one
    request for one directory, however deep the tree below it is.

    The grid's selection is emptied with every listing. Left alone, the prop
    keeps naming a row of the previous directory, and "Use" would commit that.
    """

    if browse_data is None:
        # mounted but not hydrated yet; `hydrate_browse_position` fires this
        # again with the real position a moment later. Fetching the data root
        # here would just be a round trip whose result is about to be replaced.
        return no_update, no_update, no_update, no_update

    path = browse_data.get("path", "")
    component_index = _matched_index()

    sisi = SpectraInspectorServerInterface()
    if not sisi.connected:
        msg = "Could not connect to spectra_inspector_server backend."
        return breadcrumb(path, DATA_ROOT_LABEL, component_index), [], [], msg

    root = data_root_label(sisi)

    try:
        listing = sisi.browse_directory(path)
    except ServerRequestError as err:
        spectraLogger.warning(f"Could not browse '{path}': {err}")
        return breadcrumb(path, root, component_index), [], [], str(err)

    return (
        breadcrumb(listing.path, root, component_index),
        _entry_rows(listing),
        [],
        browse_status(listing.dataset_count, listing.spectrum_count),
    )


clientside_callback(
    ClientsideFunction(namespace="dataset_table", function_name="quick_filter"),
    Output({"type": _IDS.entries, "index": MATCH}, "dashGridOptions"),
    Input({"type": _IDS.filter, "index": MATCH}, "value"),
    State({"type": _IDS.entries, "index": MATCH}, "dashGridOptions"),
)

# a filter typed for one directory says nothing about the next
clientside_callback(
    ClientsideFunction(namespace="dataset_table", function_name="clear"),
    Output({"type": _IDS.filter, "index": MATCH}, "value"),
    Input({"type": _IDS.browsestore, "index": MATCH}, "data"),
    prevent_initial_call=True,
)


def selected_entry(selected_rows: list[dict] | dict | None) -> dict | None:
    """The subdirectory selected in the grid, as its row."""
    if not selected_rows or isinstance(selected_rows, dict):
        return None
    row = selected_rows[0]
    return row if row.get("path") else None


@callback(
    Output({"type": _IDS.use, "index": MATCH}, "children"),
    Input({"type": _IDS.entries, "index": MATCH}, "selectedRows"),
)
def label_use_button(selected_rows: list[dict] | None):
    """Say on the button what it will commit."""
    entry = selected_entry(selected_rows)
    if entry is None:
        return USE_CURRENT_LABEL
    return f'Use "{entry.get("name") or entry["path"]}"'


@callback(
    Output({"type": _IDS.modal, "index": MATCH}, "is_open"),
    Input({"type": _IDS.open, "index": MATCH}, "n_clicks"),
    Input({"type": _IDS.cancel, "index": MATCH}, "n_clicks"),
    Input({"type": _IDS.committedstore, "index": MATCH}, "data"),
    prevent_initial_call=True,
)
def toggle_directory_dialog(n_open: int, n_cancel: int, committed: dict | None):
    """Open on "Change…", close on "Cancel" and once a directory is committed.
    A scan that failed commits nothing, so the dialog stays up with its error."""
    triggered = (ctx.triggered_id or {}).get("type")
    if triggered == _IDS.open:
        return True if n_open else no_update
    if triggered == _IDS.cancel:
        return False if n_cancel else no_update
    if triggered == _IDS.committedstore and committed:
        return False
    return no_update


@callback(
    Output({"type": _IDS.current, "index": MATCH}, "children"),
    Output({"type": _IDS.loaded, "index": MATCH}, "children"),
    Input(USER_STORE_DIV_ID, "data"),
    Input({"type": _IDS.div, "index": MATCH}, "id"),
    State({"type": _IDS.rootstore, "index": MATCH}, "data"),
)
def show_committed_directory(user_data: dict | None, _div_id: dict, root: str | None):
    """The line on the page: the directory in use and what was loaded from it.

    It follows the user store, so it is right on a freshly mounted page and
    recounts when the mode flips between datasets and spectra. The div's static
    id is only there to anchor the MATCH.
    """
    store = UserStore(**(user_data or {}))
    if store.working_directory is None:
        return NO_DIRECTORY_LABEL, ""
    status = committed_status(user_data)
    return (
        path_label(store.working_directory, root=root),
        status if status is not None else "",
    )


@callback(
    Output(
        {"type": _datasetIDS.dropdown, "index": MATCH}, "options", allow_duplicate=True
    ),
    Output({"type": _IDS.status, "index": MATCH}, "children", allow_duplicate=True),
    Output({"type": _IDS.committedstore, "index": MATCH}, "data"),
    Output({"type": _datasetIDS.liststore, "index": MATCH}, "data"),
    Input({"type": _IDS.use, "index": MATCH}, "n_clicks"),
    State({"type": _IDS.browsestore, "index": MATCH}, "data"),
    State({"type": _IDS.recursive, "index": MATCH}, "value"),
    State({"type": _datasetIDS.spectrumonly, "index": MATCH}, "value"),
    State({"type": _IDS.entries, "index": MATCH}, "selectedRows"),
    prevent_initial_call=True,
)
def use_directory(
    n_clicks: int,
    browse_data: dict | None,
    recursive: bool,
    spectrum_only: bool | None = False,
    selected_rows: list[dict] | None = None,
):
    """Scan a directory on the server and load what it holds into the dataset
    selector sitting next to this component: the subdirectory selected in the
    grid, or the browsed directory itself when none is. This is the one place
    a subtree is walked, and only when ``recursive`` asks for it.

    Everything the rest of the app needs goes into the committed store rather
    than straight into the user store: every output here has to carry the same
    MATCH keys, and the user store is a plain id. `store_working_directory`
    picks it up from there. The status output is the dialog's, for a scan that
    failed.

    This sets the dropdown's options but deliberately leaves its *value* alone;
    `store_working_directory` clears that, and the note there explains why the
    order matters.

    The options follow the "Spectrum only" switch sitting in the same selector,
    while both name lists go into the selector's list store so that flipping
    the switch afterwards needs no rescan.
    """

    if not n_clicks:
        return no_update, no_update, no_update, no_update

    entry = selected_entry(selected_rows)
    path = entry["path"] if entry else (browse_data or {}).get("path", "")
    sisi = SpectraInspectorServerInterface()

    try:
        available = sisi.get_datasets_in_directory(path, recursive=bool(recursive))
    except ServerRequestError as err:
        spectraLogger.warning(f"Could not scan '{path}': {err}")
        return no_update, str(err), no_update, no_update

    lists = list_store_data(available)
    available_files = lists["available_files"]
    available_spectra = lists["available_spectra"]
    spectraLogger.info(
        f"'{path}' provided {len(available_files)} datasets and "
        f"{len(available_spectra)} spectra"
    )

    shown = dataset_names(lists, bool(spectrum_only))

    return (
        dropdown_options(shown),
        # the dialog closes on a commit; what was loaded is reported on the
        # page, by `show_committed_directory`
        "",
        {
            "path": path,
            "recursive": bool(recursive),
            "available_files": available_files,
            "available_spectra": available_spectra,
            "sample_metadata": sample_metadata_for_store(available.sample_metadata),
            "truncated": available.truncated,
        },
        lists,
    )


@callback(
    Output(USER_STORE_DIV_ID, "data", allow_duplicate=True),
    Output({"type": _datasetIDS.dropdown, "index": ALL}, "value", allow_duplicate=True),
    Input({"type": _IDS.committedstore, "index": ALL}, "data"),
    State(USER_STORE_DIV_ID, "data"),
    prevent_initial_call=True,
)
def store_working_directory(
    committed: list[dict | None], current_user_data: dict | None
):
    """Carry a committed directory into the shared user store, and clear the
    sample dropdown, whose previous selection is no longer loaded.

    Split out of `use_directory` because the user store has a plain id, which
    cannot share a callback with MATCH outputs. ALL, unlike MATCH, *is* allowed
    alongside a plain output, which is what lets the dropdown be cleared here.

    Clearing it here rather than in `use_directory` is what keeps the write
    below from being thrown away. `pages/data_selection.update_selected_dataset`
    also writes the whole user store, triggered by that same dropdown value, and
    it rebuilds the dict from a `State` snapshot. Fired as a sibling of this
    callback it would snapshot the store before this write lands and clobber it
    (`working_directory` came back None every time); chained after it, it reads
    the store this callback just wrote.
    """

    payload = _triggered_commit(committed)
    n_dropdowns = len(ctx.outputs_list[1]) if len(ctx.outputs_list) > 1 else 0
    if not payload:
        return no_update, [no_update] * n_dropdowns

    new_user_data = updateDataStore(
        current_user_data or {}, "working_directory", payload.get("path", "")
    )
    new_user_data = updateDataStore(
        new_user_data,
        "working_directory_recursive",
        bool(payload.get("recursive", True)),
    )
    new_user_data = updateDataStore(
        new_user_data, "available_files", payload.get("available_files") or []
    )
    new_user_data = updateDataStore(
        new_user_data, "available_spectra", payload.get("available_spectra") or []
    )
    new_user_data = updateDataStore(
        new_user_data, "sample_metadata", payload.get("sample_metadata")
    )
    new_user_data = updateDataStore(
        new_user_data, "truncated", bool(payload.get("truncated"))
    )
    # the previous selection came from a directory that is no longer loaded
    new_user_data = updateDataStore(new_user_data, "selected_dataset", "none")
    new_user_data = updateDataStore(new_user_data, "metadata_json", "")
    return new_user_data, [None] * n_dropdowns


@callback(
    Output(RECENT_STORE_ID, "data"),
    Input({"type": _IDS.committedstore, "index": ALL}, "data"),
    State(RECENT_STORE_ID, "data"),
    prevent_initial_call=True,
)
def store_recent_directory(committed: list[dict | None], recent: list[str] | None):
    """Put a committed directory at the head of the browser's recent list."""
    payload = _triggered_commit(committed)
    if not payload:
        return no_update
    updated = remember_directory(recent, payload.get("path", ""))
    return no_update if updated == recent else updated


@callback(
    Output({"type": _IDS.recent, "index": MATCH}, "children"),
    Input(RECENT_STORE_ID, "data"),
    Input({"type": _IDS.div, "index": MATCH}, "id"),
)
def show_recent_directories(recent: list[str] | None, _div_id: dict):
    """Render the recent list; the div's static id only anchors the MATCH."""
    return recent_directories(recent, _matched_index())


def _triggered_commit(committed: list[dict | None]) -> dict | None:
    """The committed-store payload that fired the callback.

    Only one selector is on screen at a time, but the input is an ALL pattern,
    so this picks the entry that actually changed rather than assuming index 0.
    """

    values = committed or []

    triggered = ctx.triggered_id
    entries = ctx.inputs_list[0] if ctx.inputs_list else []
    if isinstance(triggered, dict) and isinstance(entries, list):
        for entry, value in zip(entries, values, strict=False):
            if isinstance(entry, dict) and entry.get("id") == triggered:
                return value

    non_empty = [v for v in values if v]
    return non_empty[-1] if non_empty else None

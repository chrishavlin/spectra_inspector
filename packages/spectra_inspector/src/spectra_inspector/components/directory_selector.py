"""A picker for the server-side working directory.

Desktop deployments point the server at a data root holding far more datasets
than a sample dropdown can usefully list, and scanning all of it at startup is
slow. In desktop mode the server defers that scan and instead lets a client walk
the tree (always within the data root) and pick one directory to scan. This
component drives that: browse with the dropdown / Up button, then commit with
"Use this directory", which repopulates the dataset selector alongside it.
"""

from typing import Any

import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, callback, ctx, dcc, html, no_update

from spectra_inspector.components.dataset_selector import (
    datasetSelectorLayoutIDs,
    format_selections,
)
from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.logging import spectraLogger
from spectra_inspector.settings import Settings
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, updateDataStore
from spectra_inspector.utilities.interface import (
    ServerRequestError,
    SpectraInspectorServerInterface,
)

DATA_ROOT_LABEL = "<data root>"


class directorySelectorLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "path",
        "entries",
        "entry",
        "up",
        "use",
        "recursive",
        "status",
        "browsestore",
        "committedstore",
    )

    def __init__(
        self, id_type_base: str = "directory-selector", index: int | None = None
    ) -> None:
        super().__init__(id_type_base, index)

    @property
    def path(self) -> str:
        return self.full_id("-path")

    @property
    def entries(self) -> str:
        return self.full_id("-entries")

    @property
    def entry(self) -> str:
        return self.full_id("-entry")

    @property
    def up(self) -> str:
        return self.full_id("-up")

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


def desktop_mode_enabled() -> bool:
    return Settings().desktop_mode


def path_label(path: str | None) -> str:
    """Human readable form of a path relative to the server data root."""
    if not path:
        return DATA_ROOT_LABEL
    return f"{DATA_ROOT_LABEL}/{path}"


def parent_path(path: str | None) -> str | None:
    """The parent of a data-root-relative path, or None at the data root.

    The server always sends these as posix paths relative to the data root, so
    the parent can be derived here without another round trip.
    """
    if not path:
        return None
    parent, _, _ = path.rpartition("/")
    return parent


def directory_selector(
    component_index: int = 0,
    enabled: bool | None = None,
) -> html.Div:
    """The working-directory picker.

    Returns an empty div outside of desktop mode, which leaves every callback
    below inert: none of their inputs exist on the page.
    """

    IDS = directorySelectorLayoutIDs(index=component_index)

    if enabled is None:
        enabled = desktop_mode_enabled()

    if not enabled:
        return html.Div(id=IDS.full_id(f"-disabled-{component_index}"))

    browse_controls = dbc.Row(
        [
            dbc.Col(
                dbc.Button(
                    "Up",
                    id=IDS.get_id_with_index("up"),
                    n_clicks=0,
                    color="secondary",
                    title="Go to the parent directory",
                ),
                width=4,
            ),
            dbc.Col(
                dbc.Button(
                    "Use this directory",
                    id=IDS.get_id_with_index("use"),
                    n_clicks=0,
                    color="primary",
                ),
                width=8,
            ),
        ],
        align="center",
        className="g-1",
    )

    # a directory can hold a lot of subdirectories, so the list scrolls rather
    # than pushing the rest of the page down.
    subdirectories = dbc.ListGroup(
        [],
        id=IDS.get_id_with_index("entries"),
        flush=True,
        style={"maxHeight": "16rem", "overflowY": "auto"},
    )

    return html.Div(
        [
            dcc.Store(
                id=IDS.get_id_with_index("browsestore"),
                storage_type="memory",
                data={"path": ""},
            ),
            dcc.Store(
                id=IDS.get_id_with_index("committedstore"),
                storage_type="memory",
                data={},
            ),
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div("Working directory: ", className="fw-bold"),
                        html.Div(
                            path_label(""),
                            id=IDS.get_id_with_index("path"),
                            style={"wordBreak": "break-all"},
                        ),
                        html.Br(),
                        browse_controls,
                        subdirectories,
                        dbc.Checkbox(
                            id=IDS.get_id_with_index("recursive"),
                            label="Include subdirectories",
                            value=True,
                        ),
                        dcc.Loading(
                            html.Div(id=IDS.get_id_with_index("status")),
                            type="circle",
                        ),
                    ]
                )
            ),
        ],
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


def entry_id(component_index: int, path: str) -> dict[str, Any]:
    """The id of one clickable subdirectory.

    The extra `name` key carries the path, so the navigation callback can read
    it straight off ctx.triggered_id. It is an ALL wildcard there, which is
    allowed alongside the MATCH on `index`.
    """
    return {"type": _IDS.entry, "index": component_index, "name": path}


def _subdir_items(listing, component_index: int) -> list:
    if not listing.directories:
        return [
            dbc.ListGroupItem(
                "No subdirectories.", disabled=True, className="text-muted"
            )
        ]

    return [
        dbc.ListGroupItem(
            d.name,
            id=entry_id(component_index, d.path),
            action=True,
            n_clicks=0,
            style={"cursor": "pointer"},
        )
        for d in listing.directories
    ]


@callback(
    Output({"type": _IDS.browsestore, "index": MATCH}, "data"),
    Input({"type": _IDS.entry, "index": MATCH, "name": ALL}, "n_clicks"),
    Input({"type": _IDS.up, "index": MATCH}, "n_clicks"),
    State({"type": _IDS.browsestore, "index": MATCH}, "data"),
    prevent_initial_call=True,
)
def navigate_directory(
    entry_clicks: list[int | None], n_up: int, browse_data: dict | None
):
    """Move the browse position down into a subdirectory or up to the parent.

    Descending is driven by clicks on the listed subdirectories rather than by a
    dropdown value: a dropdown would need clearing after each navigation, and
    clearing it from the callback that renders the listing is a dependency cycle
    (browse store -> dropdown value -> browse store).
    """

    triggered = ctx.triggered_id or {}

    if triggered.get("type") == _IDS.up:
        parent = parent_path((browse_data or {}).get("path", ""))
        if not n_up or parent is None:
            # already at the data root
            return no_update
        return {"path": parent}

    if triggered.get("type") != _IDS.entry:
        return no_update

    if not any(entry_clicks or []):
        # the list was just re-rendered, which fires this with every count at 0
        return no_update

    return {"path": triggered.get("name", "")}


@callback(
    Output({"type": _IDS.path, "index": MATCH}, "children"),
    Output({"type": _IDS.entries, "index": MATCH}, "children"),
    Output({"type": _IDS.up, "index": MATCH}, "disabled"),
    Output({"type": _IDS.status, "index": MATCH}, "children"),
    Input({"type": _IDS.browsestore, "index": MATCH}, "data"),
)
def show_directory_listing(browse_data: dict | None):
    """Fetch the listing for the current browse position and render it."""

    path = (browse_data or {}).get("path", "")
    at_root = parent_path(path) is None
    component_index = _matched_index()

    sisi = SpectraInspectorServerInterface()
    if not sisi.connected:
        msg = "Could not connect to spectra_inspector_server backend."
        return path_label(path), [], at_root, html.Div(msg)

    try:
        listing = sisi.browse_directory(path)
    except ServerRequestError as err:
        spectraLogger.warning(f"Could not browse '{path}': {err}")
        return path_label(path), [], at_root, html.Div(str(err))

    n_sets = listing.dataset_count
    plural = "" if n_sets == 1 else "s"
    status = f"{n_sets} dataset{plural} directly in this directory."

    return (
        path_label(listing.path),
        _subdir_items(listing, component_index),
        listing.parent_path is None,
        html.Div(status),
    )


@callback(
    Output(
        {"type": _datasetIDS.dropdown, "index": MATCH}, "options", allow_duplicate=True
    ),
    Output(
        {"type": _datasetIDS.dropdown, "index": MATCH}, "value", allow_duplicate=True
    ),
    Output({"type": _IDS.status, "index": MATCH}, "children", allow_duplicate=True),
    Output({"type": _IDS.committedstore, "index": MATCH}, "data"),
    Input({"type": _IDS.use, "index": MATCH}, "n_clicks"),
    State({"type": _IDS.browsestore, "index": MATCH}, "data"),
    State({"type": _IDS.recursive, "index": MATCH}, "value"),
    prevent_initial_call=True,
)
def use_directory(n_clicks: int, browse_data: dict | None, recursive: bool):
    """Scan the browsed directory on the server and load what it holds into the
    sample dropdown sitting next to this component.

    Everything the rest of the app needs goes into the committed store rather
    than straight into the user store: every output here has to carry the same
    MATCH keys, and the user store is a plain id. `store_working_directory`
    picks it up from there.
    """

    if not n_clicks:
        return no_update, no_update, no_update, no_update

    path = (browse_data or {}).get("path", "")
    sisi = SpectraInspectorServerInterface()

    try:
        available = sisi.get_datasets_in_directory(path, recursive=bool(recursive))
    except ServerRequestError as err:
        spectraLogger.warning(f"Could not scan '{path}': {err}")
        return no_update, no_update, html.Div(str(err)), no_update

    available_files = available.available_files
    spectraLogger.info(f"'{path}' provided {len(available_files)} datasets")

    plural = "" if len(available_files) == 1 else "s"
    status = f"Loaded {len(available_files)} dataset{plural} from {path_label(path)}."

    return (
        format_selections(["none", *available_files]),
        None,
        html.Div(status),
        {
            "path": path,
            "available_files": available_files,
            "sample_metadata": available.sample_metadata,
        },
    )


@callback(
    Output(USER_STORE_DIV_ID, "data", allow_duplicate=True),
    Input({"type": _IDS.committedstore, "index": ALL}, "data"),
    State(USER_STORE_DIV_ID, "data"),
    prevent_initial_call=True,
)
def store_working_directory(
    committed: list[dict | None], current_user_data: dict | None
):
    """Carry a committed directory into the shared user store.

    Split out of `use_directory` because the user store has a plain id, which
    cannot share a callback with MATCH outputs.
    """

    payload = _triggered_commit(committed)
    if not payload:
        return no_update

    new_user_data = updateDataStore(
        current_user_data or {}, "working_directory", payload.get("path", "")
    )
    new_user_data = updateDataStore(
        new_user_data, "available_files", payload.get("available_files") or []
    )
    new_user_data = updateDataStore(
        new_user_data, "sample_metadata", payload.get("sample_metadata")
    )
    # the previous selection came from a directory that is no longer loaded
    new_user_data = updateDataStore(new_user_data, "selected_dataset", "none")
    return updateDataStore(new_user_data, "metadata_json", "")


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

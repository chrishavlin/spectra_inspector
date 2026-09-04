"""The sample dropdown, with its refresh button and "Spectrum only" switch.

The server lists two kinds of dataset: maps (a full EDAX file set) and spectra
(every ``.spc``, whether standalone or part of a set). The switch picks which
list the dropdown shows. Only one of the two is shown at a time -- a standalone
``.spc`` never appears in the map list -- and the same name means a different
thing in each mode, so flipping the switch drops the current selection.

Both lists are kept in a page-local store next to the dropdown so that a flip
costs no round trip, and the mode itself lives in the user store, where the
inspector reads it to skip the image panels.
"""

from typing import Any

import dash_bootstrap_components as dbc
import requests
from dash import ALL, MATCH, Input, Output, State, callback, dcc, html, no_update
from dash.dcc import Dropdown
from dash_bootstrap_components import Button, Col, Row

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.user_store_model import USER_STORE_DIV_ID, updateDataStore
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import AvailableDatasets

SPECTRUM_ONLY_LABEL = "Spectrum only"


class datasetSelectorLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = ("dropdown", "refresh", "spectrumonly", "liststore")

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

    @property
    def spectrumonly(self) -> str:
        return self.full_id("-spectrumonly")

    @property
    def liststore(self) -> str:
        return self.full_id("-liststore")


def _format_selection(value: str) -> dict[str, Any]:
    # a plain string label on purpose: a component here (this used to be an
    # html.Span for styling) is mounted by dash-renderer with a path into the
    # layout tree, and once a callback has replaced the options that path is
    # stale, so opening the menu again crashed the renderer -- which re-mounted
    # the page from the stale layout and flipped the mode switch back.
    return {"label": value, "value": value}


def format_selections(values: list[str]) -> list[dict[str, Any]]:
    return [_format_selection(fi) for fi in values]


def list_store_data(available: AvailableDatasets | None) -> dict[str, list[str]]:
    """Both name lists of a dataset listing, as the page-local store holds them."""
    if available is None:
        return {"available_files": [], "available_spectra": []}
    return {
        "available_files": list(available.available_files),
        "available_spectra": list(available.available_spectra or []),
    }


def dataset_names(
    available: AvailableDatasets | dict[str, Any] | None, spectrum_only: bool
) -> list[str]:
    """The names the dropdown lists in a mode: spectra or maps, never both."""
    listing = (
        list_store_data(available) if not isinstance(available, dict) else available
    )
    key = "available_spectra" if spectrum_only else "available_files"
    return list(listing.get(key) or [])


def dropdown_options(names: list[str]) -> list[dict[str, Any]]:
    return format_selections(["none", *names])


def resolve_spectrum_only(user_data: dict | None, switch_value: Any) -> bool:
    """The mode in effect: the user store's, or the switch as the page rendered
    it while the store has not been written yet (a fresh session opened on an
    inspector URL that carries the mode)."""
    store = user_data or {}
    if "spectrum_only" in store:
        return bool(store["spectrum_only"])
    return bool(switch_value)


def dataset_selector(
    sisi: SpectraInspectorServerInterface,
    component_index: int = 0,
    sample_id: str | None = None,
    dropdown_label: str = "Select a sample: ",
    spectrum_only: bool = False,
) -> tuple[html.Div, AvailableDatasets | None]:
    datasets = None

    dataset_selector_IDS = datasetSelectorLayoutIDs(index=component_index)

    # ask for the datasets directly rather than probing /info first: a failed
    # connection shows up here just as well, and it saves a round trip on every
    # page render.
    try:
        datasets = sisi.get_available_datasets()
    except requests.exceptions.RequestException:
        datasets = None

    if datasets is not None:
        _menu_items = dropdown_options(dataset_names(datasets, spectrum_only))
        placeholder = "Select a spectrum" if spectrum_only else "Select an EDAX set"
        _data_selector = html.Div(
            [
                dcc.Store(
                    id=dataset_selector_IDS.get_id_with_index("liststore"),
                    storage_type="memory",
                    data=list_store_data(datasets),
                ),
                Row(
                    [
                        Col(dropdown_label, width=7),
                        Col(
                            dbc.Switch(
                                id=dataset_selector_IDS.get_id_with_index(
                                    "spectrumonly"
                                ),
                                label=SPECTRUM_ONLY_LABEL,
                                value=spectrum_only,
                            ),
                            width=5,
                        ),
                    ]
                ),
                Row(
                    [
                        Col(
                            Dropdown(
                                _menu_items,
                                id=dataset_selector_IDS.get_id_with_index("dropdown"),
                                placeholder=f"{placeholder} to load",
                                value=sample_id,
                                # the control is white in both themes while the
                                # value text inherits the body colour, which the
                                # dark theme makes white too.
                                style={"width": "100%", "color": "#212529"},
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


_IDS = datasetSelectorLayoutIDs()


@callback(
    Output({"type": _IDS.spectrumonly, "index": MATCH}, "value"),
    Input({"type": _IDS.liststore, "index": MATCH}, "id"),
    State(USER_STORE_DIV_ID, "data"),
)
def hydrate_spectrum_only(_store_id: dict, user_data: dict | None):
    """Put a freshly mounted switch into the mode the session is already in.

    Pages are rebuilt on every navigation, and the layout can only render the
    switch from the URL (the inspector's ``?spectrum_only=true``) or off. The
    user store outlives pages, so it wins when it has been written; before
    that, the switch stays as rendered and `toggle_spectrum_only` adopts it.
    """
    store = user_data or {}
    if "spectrum_only" not in store:
        return no_update
    return bool(store["spectrum_only"])


@callback(
    Output(USER_STORE_DIV_ID, "data", allow_duplicate=True),
    Output({"type": _IDS.dropdown, "index": ALL}, "options", allow_duplicate=True),
    Output({"type": _IDS.dropdown, "index": ALL}, "value", allow_duplicate=True),
    Input({"type": _IDS.spectrumonly, "index": ALL}, "value"),
    State({"type": _IDS.liststore, "index": ALL}, "data"),
    State(USER_STORE_DIV_ID, "data"),
    prevent_initial_call=True,
)
def toggle_spectrum_only(
    switch_values: list[Any],
    list_data: list[dict | None],
    user_data: dict | None,
):
    """Switch the dropdown between the map and spectrum lists.

    ALL rather than MATCH so the user store (a plain id) can be an output too;
    there is only ever one selector on a page. Three situations arrive here:

    - the store has no mode yet (fresh session): adopt the switch as rendered,
      keeping whatever the URL selected;
    - the store already holds this mode (`hydrate_spectrum_only` just set the
      switch, or a page mounted in the right mode): make sure the options match
      and leave the selection alone;
    - the user flipped the switch: the same name now means the other kind of
      dataset, so clear the selection along with the options. The dropdown
      value is an input of each page's `update_selected_dataset`, which chains
      that callback after this one so it reads the store written here.
    """
    n = len(switch_values)
    if n == 0:
        return no_update, [], []

    spectrum_only = bool(switch_values[-1])
    options = [
        dropdown_options(dataset_names(listing or {}, spectrum_only))
        for listing in list_data
    ]
    store = dict(user_data or {})

    if "spectrum_only" not in store:
        new_store = updateDataStore(store, "spectrum_only", spectrum_only)
        return new_store, options, [no_update] * n

    if bool(store["spectrum_only"]) == spectrum_only:
        return no_update, options, [no_update] * n

    new_store = updateDataStore(store, "spectrum_only", spectrum_only)
    new_store = updateDataStore(new_store, "selected_dataset", "none")
    new_store = updateDataStore(new_store, "metadata_json", "")
    return new_store, options, [None] * n

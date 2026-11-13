import json

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pytest
from dash import dcc, html, no_update
from dash._callback_context import context_value
from dash._utils import AttributeDict

# the components package re-exports the directory_selector *function* under the
# module's own name, so these have to come off the module path directly.
from spectra_inspector.components.directory_selector import (
    NO_DIRECTORY_LABEL,
    USE_CURRENT_LABEL,
    breadcrumb,
    browse_status,
    committed_status,
    crumb_id,
    data_root_label,
    directory_selector,
    directorySelectorLayoutIDs,
    hydrate_browse_position,
    label_use_button,
    loaded_status,
    navigate_directory,
    path_label,
    selected_entry,
    show_committed_directory,
    show_directory_listing,
    store_working_directory,
    toggle_directory_dialog,
    use_directory,
)
from spectra_inspector.utilities.interface import ServerRequestError
from spectra_inspector.utilities.model import (
    AvailableDatasets,
    directoryEntry,
    directoryListing,
)

_INTERFACE_PATH = (
    "spectra_inspector.components.directory_selector.SpectraInspectorServerInterface"
)


def _set_triggered(prop_id: str) -> None:
    context_value.set(AttributeDict(triggered_inputs=[{"prop_id": prop_id}]))


@pytest.fixture(autouse=True)
def _clear_context():
    yield
    context_value.set(AttributeDict(triggered_inputs=[]))


@pytest.fixture(autouse=True)
def _desktop_mode_off(mocker):
    # `data_root_label` reads Settings(), so these would otherwise depend on
    # whether the developer's .env happens to switch desktop mode on -- CI has
    # no .env and passes either way. The tests that want it on re-patch over
    # this with `_mock_settings`.
    _mock_settings(mocker, False)


def test_directory_selector_layout_ids():
    ids = directorySelectorLayoutIDs(index=0)
    for prop in ids.prop_names:
        assert prop in getattr(ids, prop)
        assert ids.get_id_with_index(prop)["index"] == 0


def test_directory_selector_hidden_outside_desktop_mode():
    div = directory_selector(component_index=0, enabled=False)
    assert isinstance(div, html.Div)
    assert not div.children


def _by_type(component) -> dict:
    return {
        c.id["type"]: c
        for c in component._traverse()
        if isinstance(getattr(c, "id", None), dict)
    }


def test_directory_selector_builds_the_line_and_the_dialog():
    div = directory_selector(component_index=1, enabled=True)
    assert isinstance(div, html.Div)
    assert div.id == {"type": "directory-selector-div", "index": 1}

    ids = directorySelectorLayoutIDs()
    parts = _by_type(div)
    # everything inside the div but the breadcrumb segments, which only exist
    # below the root
    expected = {getattr(ids, p) for p in ids.prop_names} - {ids.div, ids.crumb}
    assert set(parts) == expected

    assert parts[ids.current].children == NO_DIRECTORY_LABEL
    modal = parts[ids.modal]
    assert isinstance(modal, dbc.Modal)
    assert modal.is_open is False
    # the browsing controls live in the dialog, the line stays on the page
    in_dialog = _by_type(modal)
    assert {ids.path, ids.filter, ids.entries, ids.use, ids.recursive} <= set(in_dialog)
    assert ids.current not in in_dialog
    assert ids.open not in in_dialog

    assert isinstance(parts[ids.entries], dag.AgGrid)
    assert parts[ids.use].children == USE_CURRENT_LABEL
    # on by default: committing a directory walks what is below it
    assert parts[ids.recursive].value is True


def test_browse_store_starts_unhydrated():
    # None is the "not hydrated yet" sentinel `show_directory_listing` waits on;
    # a hardcoded path here is what used to reset the picker on a page switch
    div = directory_selector(component_index=0, enabled=True)
    browse_store = _by_type(div)["directory-selector-browsestore"]
    assert isinstance(browse_store, dcc.Store)
    assert browse_store.data is None


@pytest.mark.parametrize(
    ("user_data", "expected"),
    [
        ({"working_directory": "session-a"}, "session-a"),
        # nothing committed yet, or committed at the data root
        ({"working_directory": None}, ""),
        ({"working_directory": ""}, ""),
        ({}, ""),
        (None, ""),
    ],
)
def test_hydrate_browse_position(user_data, expected):
    div_id = {"type": "directory-selector-div", "index": 1}
    assert hydrate_browse_position(div_id, user_data) == {"path": expected}


def test_show_directory_listing_waits_for_hydration(mocker):
    sisi = _mock_interface(mocker, browse_directory=mocker.MagicMock())
    _set_outputs_for_index(0)

    assert all(out is no_update for out in show_directory_listing(None))
    sisi.browse_directory.assert_not_called()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (None, "<data root>"),
        ("", "<data root>"),
        ("a", "<data root>/a"),
        ("a/b", "<data root>/a/b"),
    ],
)
def test_path_label(path, expected):
    assert path_label(path) == expected


@pytest.mark.parametrize(
    ("root", "path", "expected"),
    [
        ("/data/edax", "", "/data/edax"),
        ("/data/edax", "a/b", "/data/edax/a/b"),
        # a root spelled with a trailing separator must not double it up
        ("/data/edax/", "a", "/data/edax/a"),
        ("/", "a", "/a"),
        # falls back to the placeholder when there is no root to show
        ("", "a", "<data root>/a"),
    ],
)
def test_path_label_with_a_root(root, path, expected):
    assert path_label(path, root=root) == expected


def _mock_settings(mocker, desktop_mode: bool) -> None:
    mocker.patch(
        "spectra_inspector.components.directory_selector.desktop_mode_enabled",
        mocker.MagicMock(return_value=desktop_mode),
    )


def test_data_root_label_outside_desktop_mode(mocker):
    # the data root is a server-side detail that a hosted client should not show
    _mock_settings(mocker, False)
    sisi = mocker.MagicMock()

    assert data_root_label(sisi) == "<data root>"
    sisi.get_info.assert_not_called()


def test_data_root_label_in_desktop_mode(mocker):
    _mock_settings(mocker, True)
    info = mocker.MagicMock(spectra_inspector_data_root="/data/edax")
    sisi = mocker.MagicMock(get_info=mocker.MagicMock(return_value=info))

    assert data_root_label(sisi) == "/data/edax"


@pytest.mark.parametrize(
    "get_info",
    [
        pytest.param(ServerRequestError("no backend"), id="request-failed"),
        pytest.param("", id="empty-root"),
    ],
)
def test_data_root_label_falls_back_to_the_placeholder(mocker, get_info):
    _mock_settings(mocker, True)
    if isinstance(get_info, ServerRequestError):
        mocked = mocker.MagicMock(side_effect=get_info)
    else:
        mocked = mocker.MagicMock(
            return_value=mocker.MagicMock(spectra_inspector_data_root=get_info)
        )
    sisi = mocker.MagicMock(get_info=mocked)

    assert data_root_label(sisi) == "<data root>"


def _crumbs(children: list) -> list[tuple[str, str | None]]:
    """(label, target path) per segment, None for the unclickable last one."""
    segments = []
    for child in children:
        if isinstance(child, dbc.Button):
            segments.append((child.children, child.id["name"]))
        elif "fw-bold" in (getattr(child, "className", "") or ""):
            segments.append((child.children, None))
    return segments


def test_breadcrumb_at_the_data_root():
    assert _crumbs(breadcrumb("", "/data/edax", 0)) == [("/data/edax", None)]
    assert _crumbs(breadcrumb(None, "<data root>", 0)) == [("<data root>", None)]


def test_breadcrumb_links_every_segment_but_the_last():
    assert _crumbs(breadcrumb("a/b/c", "/data/edax", 0)) == [
        ("/data/edax", ""),
        ("a", "a"),
        ("b", "a/b"),
        ("c", None),
    ]


def test_breadcrumb_carries_the_component_index():
    # the picker is index 1 on the inspector page, and the segments have to
    # carry that index or MATCH will never pair them with the store
    buttons = [c for c in breadcrumb("a/b", "root", 1) if isinstance(c, dbc.Button)]
    assert [b.id for b in buttons] == [crumb_id(1, ""), crumb_id(1, "a")]
    assert crumb_id(1, "a/b") == {
        "type": "directory-selector-crumb",
        "index": 1,
        "name": "a/b",
    }


def _set_triggered_id(component_id: dict, prop: str) -> None:
    serialized = json.dumps(component_id, separators=(",", ":"), sort_keys=True)
    context_value.set(
        AttributeDict(triggered_inputs=[{"prop_id": f"{serialized}.{prop}"}])
    )


_ENTRIES_ID = {"type": "directory-selector-entries", "index": 0}
_COMMITTED_ID = {"type": "directory-selector-committedstore", "index": 0}


def test_double_click_descends():
    _set_triggered_id(_ENTRIES_ID, "cellDoubleClicked")
    cell = {"rowId": "a/b", "value": "b"}
    assert navigate_directory(cell, [], {}, {"path": "a"}) == {"path": "a/b"}
    assert navigate_directory(None, [], {}, {"path": "a"}) is no_update


def test_breadcrumb_click_moves_up():
    _set_triggered_id(crumb_id(0, "a"), "n_clicks")
    assert navigate_directory(None, [0, 1], {}, {"path": "a/b/c"}) == {"path": "a"}

    _set_triggered_id(crumb_id(0, ""), "n_clicks")
    assert navigate_directory(None, [1, 0], {}, {"path": "a/b/c"}) == {"path": ""}


def test_navigate_ignores_a_freshly_rendered_breadcrumb():
    # re-rendering the breadcrumb fires this with every count still at 0
    _set_triggered_id(crumb_id(0, "a"), "n_clicks")
    assert navigate_directory(None, [0, 0], {}, {"path": "a/b"}) is no_update
    assert navigate_directory(None, [], {}, {"path": "a/b"}) is no_update


def test_browse_position_follows_a_commit():
    # "Use" may commit a subdirectory selected in the grid, and the dialog
    # should then reopen on what is in use
    _set_triggered_id(_COMMITTED_ID, "data")
    commit = {"path": "a/b"}
    assert navigate_directory(None, [], commit, {"path": "a"}) == {"path": "a/b"}
    assert navigate_directory(None, [], commit, {"path": "a/b"}) is no_update
    assert navigate_directory(None, [], {}, {"path": "a"}) is no_update


_LISTING = directoryListing(
    path="session-a",
    name="session-a",
    parent_path="",
    directories=[directoryEntry(name="nested", path="session-a/nested")],
    dataset_count=1,
    spectrum_count=3,
)


def _mock_interface(mocker, **attrs):
    sisi = mocker.MagicMock()
    sisi.connected = True
    for key, value in attrs.items():
        setattr(sisi, key, value)
    mocker.patch(
        _INTERFACE_PATH,
        mocker.MagicMock(return_value=sisi),
    )
    return sisi


def _set_outputs_for_index(component_index: int) -> None:
    context_value.set(
        AttributeDict(
            triggered_inputs=[],
            outputs_list=[
                {
                    "id": {"type": "directory-selector-path", "index": component_index},
                    "property": "children",
                }
            ],
        )
    )


def test_show_directory_listing(mocker):
    sisi = _mock_interface(
        mocker, browse_directory=mocker.MagicMock(return_value=_LISTING)
    )
    _set_outputs_for_index(0)

    crumbs, rows, selected, count = show_directory_listing({"path": "session-a"})

    # one listing of one directory, nothing below it
    sisi.browse_directory.assert_called_once_with("session-a")
    sisi.get_datasets_in_directory.assert_not_called()

    assert _crumbs(crumbs) == [("<data root>", ""), ("session-a", None)]
    assert rows == [{"name": "nested", "path": "session-a/nested"}]
    # a selection left from the previous directory must not survive
    assert selected == []
    assert count == "This directory: 1 dataset, 3 spectra."


def test_show_directory_listing_shows_the_real_root_in_desktop_mode(mocker):
    _mock_settings(mocker, True)
    info = mocker.MagicMock(spectra_inspector_data_root="/data/edax")
    _mock_interface(
        mocker,
        browse_directory=mocker.MagicMock(return_value=_LISTING),
        get_info=mocker.MagicMock(return_value=info),
    )
    _set_outputs_for_index(0)

    crumbs, _, _, _ = show_directory_listing({"path": "session-a"})

    assert _crumbs(crumbs)[0] == ("/data/edax", "")


def test_show_directory_listing_uses_the_matched_index(mocker):
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=_LISTING))
    _set_outputs_for_index(1)

    crumbs, _, _, _ = show_directory_listing({"path": "session-a"})

    assert [c.id["index"] for c in crumbs if isinstance(c, dbc.Button)] == [1]


def test_show_directory_listing_with_no_subdirectories(mocker):
    leaf = directoryListing(path="a", name="a", parent_path="", dataset_count=3)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=leaf))
    _set_outputs_for_index(0)

    _, rows, _, count = show_directory_listing({"path": "a"})

    assert rows == []
    assert count == "This directory: 3 datasets, 0 spectra."


def test_show_directory_listing_at_the_data_root(mocker):
    root = directoryListing(path="", name="root", parent_path=None, dataset_count=0)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=root))
    _set_outputs_for_index(0)

    crumbs, rows, _, _ = show_directory_listing({"path": ""})

    assert _crumbs(crumbs) == [("<data root>", None)]
    assert rows == []


def test_show_directory_listing_reports_server_errors(mocker):
    err = ServerRequestError("directory browsing requires DESKTOP_MODE")
    _mock_interface(mocker, browse_directory=mocker.MagicMock(side_effect=err))
    _set_outputs_for_index(0)

    crumbs, rows, selected, count = show_directory_listing({"path": "a"})

    # still a way back up from a directory that could not be listed
    assert _crumbs(crumbs) == [("<data root>", ""), ("a", None)]
    assert rows == []
    assert selected == []
    assert "DESKTOP_MODE" in count


def test_show_directory_listing_without_a_backend(mocker):
    sisi = mocker.MagicMock()
    sisi.connected = False
    mocker.patch(_INTERFACE_PATH, mocker.MagicMock(return_value=sisi))

    _set_outputs_for_index(0)

    _, rows, _, count = show_directory_listing({"path": ""})

    assert rows == []
    assert "Could not connect" in count


def test_selected_entry():
    row = {"name": "nested", "path": "a/nested"}
    assert selected_entry([row]) == row
    assert selected_entry([]) is None
    assert selected_entry(None) is None


def test_use_button_says_what_it_commits():
    assert label_use_button([{"name": "nested", "path": "a/nested"}]) == 'Use "nested"'
    assert label_use_button([]) == USE_CURRENT_LABEL
    assert label_use_button(None) == USE_CURRENT_LABEL


def _dialog_id(prop: str) -> dict:
    return {"type": f"directory-selector-{prop}", "index": 0}


def test_dialog_opens_and_cancels():
    _set_triggered_id(_dialog_id("open"), "n_clicks")
    assert toggle_directory_dialog(1, 0, {}) is True
    assert toggle_directory_dialog(0, 0, {}) is no_update

    _set_triggered_id(_dialog_id("cancel"), "n_clicks")
    assert toggle_directory_dialog(1, 1, {}) is False


def test_dialog_closes_on_a_commit_only():
    _set_triggered_id(_COMMITTED_ID, "data")
    assert toggle_directory_dialog(1, 0, {"path": "a"}) is False
    # the store's empty initial value is not a commit
    assert toggle_directory_dialog(1, 0, {}) is no_update


def test_use_directory_populates_the_sample_dropdown(mocker):
    available = AvailableDatasets(
        available_files=["C-1", "C-2"],
        sample_metadata={"records": [], "map_samples": {}},
        directory="session-a",
    )
    sisi = _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    options, status, committed, lists = use_directory(1, {"path": "session-a"}, True)

    sisi.get_datasets_in_directory.assert_called_once_with("session-a", recursive=True)

    assert [o["value"] for o in options] == ["none", "C-1", "C-2"]
    # nothing to report in the dialog, which closes on the commit
    assert status == ""
    assert committed == {
        "path": "session-a",
        "recursive": True,
        "available_files": ["C-1", "C-2"],
        "available_spectra": [],
        "sample_metadata": {"records": [], "map_samples": {}},
        "truncated": False,
    }
    assert lists == {
        "available_files": ["C-1", "C-2"],
        "available_spectra": [],
        "sample_metadata": committed["sample_metadata"],
        "truncated": False,
    }


def test_use_directory_commits_the_selected_subdirectory(mocker):
    available = AvailableDatasets(available_files=["C-1"])
    sisi = _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    selected = [{"name": "nested", "path": "session-a/nested"}]
    _, _, committed, _ = use_directory(
        1, {"path": "session-a"}, True, selected_rows=selected
    )

    sisi.get_datasets_in_directory.assert_called_once_with(
        "session-a/nested", recursive=True
    )
    assert committed["path"] == "session-a/nested"


def test_use_directory_passes_the_recursive_flag(mocker):
    available = AvailableDatasets(available_files=["C-1"])
    sisi = _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    _, _, committed, _ = use_directory(1, {"path": "session-a"}, False)

    sisi.get_datasets_in_directory.assert_called_once_with("session-a", recursive=False)
    assert committed["recursive"] is False


def test_use_directory_carries_a_truncated_scan(mocker):
    # the server stopped at SPECTRA_INSPECTOR_MAX_DATASETS, so the listing is
    # the first N of a larger number on disk
    available = AvailableDatasets(
        available_files=["C-1", "C-2"],
        directory="session-a",
        truncated=True,
    )
    _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    options, _, committed, lists = use_directory(1, {"path": "session-a"}, True)

    # the datasets that did come back are still usable
    assert [o["value"] for o in options] == ["none", "C-1", "C-2"]
    assert committed["truncated"] is True
    assert lists["truncated"] is True


def test_use_directory_without_a_click_does_nothing(mocker):
    sisi = _mock_interface(mocker, get_datasets_in_directory=mocker.MagicMock())

    assert all(out is no_update for out in use_directory(0, {"path": "a"}, True))
    sisi.get_datasets_in_directory.assert_not_called()


def test_use_directory_reports_server_errors(mocker):
    err = ServerRequestError("'nope' is not a directory")
    _mock_interface(mocker, get_datasets_in_directory=mocker.MagicMock(side_effect=err))

    options, status, committed, lists = use_directory(1, {"path": "nope"}, True)

    assert options is no_update
    assert committed is no_update
    assert lists is no_update
    assert "not a directory" in status


_SPECTRA = AvailableDatasets(
    available_files=["C-1"],
    available_spectra=["C-1", "S-1"],
    directory="session-a",
)


def test_use_directory_in_spectrum_only_mode(mocker):
    _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=_SPECTRA)
    )

    options, _, committed, lists = use_directory(
        1, {"path": "session-a"}, True, spectrum_only=True
    )

    # every .spc, the set's own one included
    assert [o["value"] for o in options] == ["none", "C-1", "S-1"]
    assert committed["available_files"] == ["C-1"]
    assert committed["available_spectra"] == ["C-1", "S-1"]
    assert lists["available_files"] == ["C-1"]
    assert lists["available_spectra"] == ["C-1", "S-1"]


def test_standalone_spectra_stay_out_of_the_map_list(mocker):
    _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=_SPECTRA)
    )

    options, _, _, lists = use_directory(
        1, {"path": "session-a"}, True, spectrum_only=False
    )

    assert [o["value"] for o in options] == ["none", "C-1"]
    # both lists are kept regardless, so flipping the switch needs no rescan
    assert lists["available_spectra"] == ["C-1", "S-1"]


def test_status_labels_count_by_kind():
    assert loaded_status(1).children == "1 dataset loaded."
    assert loaded_status(1, spectrum_only=True).children == "1 spectrum loaded."
    assert loaded_status(3, spectrum_only=True).children == "3 spectra loaded."
    assert browse_status(2, 1) == "This directory: 2 datasets, 1 spectrum."


def test_loaded_status_warns_about_a_truncated_scan():
    status = loaded_status(2, truncated=True)
    assert "first 2 datasets" in status.children
    assert "Pick a subdirectory" in status.children
    assert "text-warning" in status.className
    # unset props are absent on a Dash component rather than None
    assert not hasattr(loaded_status(2), "className")


_COMMITTED_STORE = {
    "working_directory": "session-a",
    "available_files": ["C-1", "C-2"],
}


def test_committed_status_counts_by_the_mode():
    store = {
        "working_directory": "",
        "available_files": ["C-1"],
        "available_spectra": ["C-1", "S-1"],
        "spectrum_only": True,
    }
    assert committed_status(store).children == "2 spectra loaded."

    store["spectrum_only"] = False
    assert committed_status(store).children == "1 dataset loaded."


@pytest.mark.parametrize(
    "store",
    [
        None,
        {},
        # working_directory defaults to None; "" is the data root, committed
        {"selected_dataset": "none"},
        {"working_directory": "a"},
    ],
)
def test_committed_status_before_a_commit(store):
    assert committed_status(store) is None


def test_the_page_line_shows_the_committed_directory():
    # built from the user store, so a fresh mount on the other page is right
    # without any memory of the commit
    label, loaded = show_committed_directory(_COMMITTED_STORE, {}, "/data/edax")
    assert label == "/data/edax/session-a"
    assert loaded.children == "2 datasets loaded."


def test_the_page_line_at_the_data_root():
    store = {"working_directory": "", "available_files": ["C-1"]}
    label, loaded = show_committed_directory(store, {}, "/data/edax")
    assert label == "/data/edax"
    assert loaded.children == "1 dataset loaded."


def test_the_page_line_before_a_commit():
    assert show_committed_directory({}, {}, "/data/edax") == (NO_DIRECTORY_LABEL, "")
    assert show_committed_directory(None, {}, None) == (NO_DIRECTORY_LABEL, "")


def test_the_page_line_keeps_the_truncation_warning():
    # the warning has to come back with the count, or a page switch quietly
    # turns "showing the first N" into "N loaded"
    store = {**_COMMITTED_STORE, "truncated": True}
    _, loaded = show_committed_directory(store, {}, None)
    assert "first 2 datasets" in loaded.children
    assert "text-warning" in loaded.className


_COMMIT = {
    "path": "session-a",
    "available_files": ["C-1", "C-2"],
    "sample_metadata": {"records": [], "map_samples": {}},
}


def _set_inputs_list(ids: list[dict], n_dropdowns: int = 1) -> None:
    context_value.set(
        AttributeDict(
            triggered_inputs=[
                {"prop_id": f"{json.dumps(ids[-1], separators=(',', ':'))}.data"}
            ],
            args_grouping=[],
            inputs_list=[[{"id": cid, "property": "data"} for cid in ids]],
            outputs_list=[
                {"id": "user-mem-store", "property": "data"},
                [
                    {
                        "id": {"type": "data-selector-dropdown", "index": i},
                        "property": "value",
                    }
                    for i in range(n_dropdowns)
                ],
            ],
        )
    )


def test_store_working_directory():
    _set_inputs_list([{"type": "directory-selector-committedstore", "index": 0}])

    user_data, dropdown_values = store_working_directory(
        [_COMMIT],
        {"selected_dataset": "stale-sample", "metadata_json": "{...}"},
    )

    assert user_data["working_directory"] == "session-a"
    assert user_data["available_files"] == ["C-1", "C-2"]
    assert user_data["available_spectra"] == []
    assert user_data["sample_metadata"] == {"records": [], "map_samples": {}}
    # the previous selection came from a directory that is no longer loaded
    assert user_data["selected_dataset"] == "none"
    assert user_data["metadata_json"] == ""
    # clearing the dropdown here, rather than in use_directory, is what chains
    # pages.data_selection.update_selected_dataset after this write instead of
    # racing it -- fired as a sibling it clobbered working_directory
    assert dropdown_values == [None]


def test_store_working_directory_clears_every_dropdown_on_the_page():
    # the output is an ALL pattern, so the return has to be sized to match
    _set_inputs_list(
        [{"type": "directory-selector-committedstore", "index": 0}], n_dropdowns=2
    )

    _, dropdown_values = store_working_directory([_COMMIT], {})

    assert dropdown_values == [None, None]


def test_store_working_directory_ignores_an_empty_commit():
    _set_inputs_list([{"type": "directory-selector-committedstore", "index": 0}])

    for committed in ([{}], []):
        user_data, dropdown_values = store_working_directory(committed, {})
        assert user_data is no_update
        assert dropdown_values == [no_update]


def test_store_working_directory_picks_the_triggering_selector():
    # the input is an ALL pattern, so it must not assume index 0
    ids = [
        {"type": "directory-selector-committedstore", "index": 0},
        {"type": "directory-selector-committedstore", "index": 1},
    ]
    _set_inputs_list(ids)

    other = {"path": "session-b", "available_files": ["C-3"], "sample_metadata": None}
    user_data, _ = store_working_directory([other, _COMMIT], {})

    assert user_data["working_directory"] == "session-a"
    assert user_data["available_files"] == ["C-1", "C-2"]


def test_store_working_directory_carries_the_spectra():
    _set_inputs_list([{"type": "directory-selector-committedstore", "index": 0}])

    commit = {**_COMMIT, "available_spectra": ["C-1", "C-2", "S-1"]}
    user_data, _ = store_working_directory([commit], {"spectrum_only": True})

    assert user_data["available_spectra"] == ["C-1", "C-2", "S-1"]
    # the mode is not the directory's business, it stays as it was
    assert user_data["spectrum_only"] is True

import json

import pytest
from dash import html, no_update
from dash._callback_context import context_value
from dash._utils import AttributeDict

# the components package re-exports the directory_selector *function* under the
# module's own name, so these have to come off the module path directly.
from spectra_inspector.components.directory_selector import (
    data_root_label,
    directory_selector,
    directorySelectorLayoutIDs,
    entry_id,
    hydrate_browse_position,
    navigate_directory,
    parent_path,
    path_label,
    show_directory_listing,
    store_working_directory,
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


def test_directory_selector_builds_controls():
    div = directory_selector(component_index=1, enabled=True)
    assert isinstance(div, html.Div)
    assert div.id == {"type": "directory-selector-div", "index": 1}
    # the two stores plus the card of controls
    assert len(div.children) == 3


def test_browse_store_starts_unhydrated():
    # None is the "not hydrated yet" sentinel `show_directory_listing` waits on;
    # a hardcoded path here is what used to reset the picker on a page switch
    div = directory_selector(component_index=0, enabled=True)
    browse_store = div.children[0]
    assert browse_store.id == {"type": "directory-selector-browsestore", "index": 0}
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

    assert all(out is no_update for out in show_directory_listing(None, None))
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


@pytest.mark.parametrize(
    ("path", "expected"),
    [(None, None), ("", None), ("a", ""), ("a/b", "a"), ("a/b/c", "a/b")],
)
def test_parent_path(path, expected):
    assert parent_path(path) == expected


def _set_triggered_entry(component_index: int, path: str) -> None:
    component_id = entry_id(component_index, path)
    serialized = json.dumps(component_id, separators=(",", ":"), sort_keys=True)
    context_value.set(
        AttributeDict(triggered_inputs=[{"prop_id": f"{serialized}.n_clicks"}])
    )


def test_entry_id_carries_the_path():
    assert entry_id(1, "a/b") == {
        "type": "directory-selector-entry",
        "index": 1,
        "name": "a/b",
    }


def test_navigate_into_subdirectory():
    _set_triggered_entry(0, "a/b")
    assert navigate_directory([0, 1], 0, {"path": "a"}) == {"path": "a/b"}


def test_navigate_ignores_a_freshly_rendered_list():
    # re-rendering the list fires this with every count still at 0
    _set_triggered_entry(0, "a/b")
    assert navigate_directory([0, 0], 0, {"path": "a"}) is no_update
    assert navigate_directory([], 0, {"path": "a"}) is no_update


def test_navigate_up():
    _set_triggered('{"index":0,"type":"directory-selector-up"}.n_clicks')
    assert navigate_directory([], 1, {"path": "a/b"}) == {"path": "a"}
    assert navigate_directory([], 1, {"path": "a"}) == {"path": ""}


def test_navigate_up_stops_at_the_data_root():
    _set_triggered('{"index":0,"type":"directory-selector-up"}.n_clicks')
    assert navigate_directory([], 1, {"path": ""}) is no_update


_LISTING = directoryListing(
    path="session-a",
    name="session-a",
    parent_path="",
    directories=[directoryEntry(name="nested", path="session-a/nested")],
    dataset_count=1,
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
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=_LISTING))
    _set_outputs_for_index(0)

    label, entries, up_disabled, status = show_directory_listing(
        {"path": "session-a"}, None
    )

    assert label == "<data root>/session-a"
    assert [e.id["name"] for e in entries] == ["session-a/nested"]
    assert [e.children for e in entries] == ["nested"]
    assert up_disabled is False
    assert "1 dataset in this directory" in status.children
    # the hint that "use this directory" is what reaches the subdirectories
    assert "subdirectories" in status.children


def test_show_directory_listing_shows_the_real_root_in_desktop_mode(mocker):
    _mock_settings(mocker, True)
    info = mocker.MagicMock(spectra_inspector_data_root="/data/edax")
    _mock_interface(
        mocker,
        browse_directory=mocker.MagicMock(return_value=_LISTING),
        get_info=mocker.MagicMock(return_value=info),
    )
    _set_outputs_for_index(0)

    label, _, _, _ = show_directory_listing({"path": "session-a"}, None)

    assert label == "/data/edax/session-a"


def test_show_directory_listing_uses_the_matched_index(mocker):
    # the picker is index 1 on the inspector page, and the clickable entries
    # have to carry that index or MATCH will never pair them with the store
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=_LISTING))
    _set_outputs_for_index(1)

    _, entries, _, _ = show_directory_listing({"path": "session-a"}, None)

    assert [e.id["index"] for e in entries] == [1]


def test_show_directory_listing_with_no_subdirectories(mocker):
    leaf = directoryListing(path="a", name="a", parent_path="", dataset_count=3)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=leaf))
    _set_outputs_for_index(0)

    _, entries, up_disabled, status = show_directory_listing({"path": "a"}, None)

    # a placeholder row, and crucially nothing carrying a clickable id
    assert len(entries) == 1
    assert entries[0].disabled is True
    assert not hasattr(entries[0], "name")
    assert up_disabled is False
    # nothing to search, so no pointer at the button that would search it
    assert status.children == "3 datasets in this directory."


def test_show_directory_listing_at_the_data_root(mocker):
    root = directoryListing(path="", name="root", parent_path=None, dataset_count=0)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=root))
    _set_outputs_for_index(0)

    label, entries, up_disabled, status = show_directory_listing({"path": ""}, None)

    assert label == "<data root>"
    assert len(entries) == 1
    assert entries[0].disabled is True
    assert up_disabled is True
    assert "0 datasets in this directory" in status.children


_COMMITTED_STORE = {
    "working_directory": "session-a",
    "available_files": ["C-1", "C-2"],
}


def test_show_directory_listing_restores_the_committed_count(mocker):
    # a fresh mount on the other page has no memory of the message
    # `use_directory` wrote, but the user store still knows what was loaded
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=_LISTING))
    _set_outputs_for_index(1)

    _, _, _, status = show_directory_listing({"path": "session-a"}, _COMMITTED_STORE)

    assert status.children == "Loaded 2 datasets from <data root>/session-a."


def test_show_directory_listing_counts_directories_that_are_not_in_use(mocker):
    # browsing away from the committed directory goes back to the plain count
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=_LISTING))
    _set_outputs_for_index(0)

    store = {**_COMMITTED_STORE, "working_directory": "session-b"}
    _, _, _, status = show_directory_listing({"path": "session-a"}, store)

    assert "1 dataset in this directory" in status.children


def test_show_directory_listing_ignores_a_store_with_nothing_committed(mocker):
    root = directoryListing(path="", name="root", parent_path=None, dataset_count=0)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=root))
    _set_outputs_for_index(0)

    # working_directory defaults to None, which reads as "" -- the data root --
    # so it must be the missing available_files that rules a commit out
    _, _, _, status = show_directory_listing({"path": ""}, {"selected_dataset": "none"})

    assert "0 datasets in this directory" in status.children


def test_show_directory_listing_restores_a_truncated_scan(mocker):
    # the warning has to come back with the count, or a page switch quietly
    # turns "showing the first N" into "loaded N"
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=_LISTING))
    _set_outputs_for_index(1)

    store = {**_COMMITTED_STORE, "truncated": True}
    _, _, _, status = show_directory_listing({"path": "session-a"}, store)

    text = " ".join(child.children for child in status.children)
    assert "first 2 datasets" in text
    assert "Pick a subdirectory" in text
    assert "text-warning" in status.className


def test_show_directory_listing_restores_a_commit_at_the_data_root(mocker):
    root = directoryListing(path="", name="root", parent_path=None, dataset_count=0)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=root))
    _set_outputs_for_index(0)

    store = {"working_directory": "", "available_files": ["C-1"]}
    _, _, _, status = show_directory_listing({"path": ""}, store)

    assert status.children == "Loaded 1 dataset from <data root>."


def test_show_directory_listing_reports_server_errors(mocker):
    err = ServerRequestError("directory browsing requires DESKTOP_MODE")
    _mock_interface(mocker, browse_directory=mocker.MagicMock(side_effect=err))
    _set_outputs_for_index(0)

    label, entries, up_disabled, status = show_directory_listing({"path": "a"}, None)

    assert label == "<data root>/a"
    assert entries == []
    assert up_disabled is False
    assert "DESKTOP_MODE" in status.children


def test_show_directory_listing_without_a_backend(mocker):
    sisi = mocker.MagicMock()
    sisi.connected = False
    mocker.patch(_INTERFACE_PATH, mocker.MagicMock(return_value=sisi))

    _set_outputs_for_index(0)

    _, entries, _, status = show_directory_listing({"path": ""}, None)

    assert entries == []
    assert "Could not connect" in status.children


def test_use_directory_populates_the_sample_dropdown(mocker):
    available = AvailableDatasets(
        available_files=["C-1", "C-2"],
        sample_metadata={"records": [], "map_samples": {}},
        directory="session-a",
    )
    sisi = _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    options, status, committed = use_directory(1, {"path": "session-a"}, True)

    sisi.get_datasets_in_directory.assert_called_once_with("session-a", recursive=True)

    assert [o["value"] for o in options] == ["none", "C-1", "C-2"]
    assert "Loaded 2 datasets" in status.children
    assert committed == {
        "path": "session-a",
        "recursive": True,
        "available_files": ["C-1", "C-2"],
        "sample_metadata": {"records": [], "map_samples": {}},
        "truncated": False,
    }


def test_use_directory_reports_the_real_root_in_desktop_mode(mocker):
    _mock_settings(mocker, True)
    info = mocker.MagicMock(spectra_inspector_data_root="/data/edax")
    _mock_interface(
        mocker,
        get_datasets_in_directory=mocker.MagicMock(
            return_value=AvailableDatasets(available_files=["C-1"])
        ),
        get_info=mocker.MagicMock(return_value=info),
    )

    _, status, _ = use_directory(1, {"path": "session-a"}, True)

    assert "from /data/edax/session-a." in status.children


def test_use_directory_passes_the_recursive_flag(mocker):
    available = AvailableDatasets(available_files=["C-1"])
    sisi = _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    _, status, _ = use_directory(1, {"path": "session-a"}, False)

    sisi.get_datasets_in_directory.assert_called_once_with("session-a", recursive=False)
    assert "Loaded 1 dataset " in status.children


def test_use_directory_warns_about_a_truncated_scan(mocker):
    # the server stopped at SPECTRA_INSPECTOR_MAX_DATASETS, so the dropdown is
    # holding the first N of a larger number on disk
    available = AvailableDatasets(
        available_files=["C-1", "C-2"],
        directory="session-a",
        truncated=True,
    )
    _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    options, status, _ = use_directory(1, {"path": "session-a"}, True)

    # the datasets that did come back are still usable
    assert [o["value"] for o in options] == ["none", "C-1", "C-2"]

    text = " ".join(child.children for child in status.children)
    assert "first 2 datasets" in text
    assert "Pick a subdirectory" in text
    assert "text-warning" in status.className


def test_use_directory_does_not_warn_on_a_complete_scan(mocker):
    available = AvailableDatasets(available_files=["C-1"], truncated=False)
    _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    _, status, _ = use_directory(1, {"path": "session-a"}, True)

    assert status.children == "Loaded 1 dataset from <data root>/session-a."
    # unset props are absent on a Dash component rather than None
    assert not hasattr(status, "className")


def test_use_directory_without_a_click_does_nothing(mocker):
    sisi = _mock_interface(mocker, get_datasets_in_directory=mocker.MagicMock())

    assert all(out is no_update for out in use_directory(0, {"path": "a"}, True))
    sisi.get_datasets_in_directory.assert_not_called()


def test_use_directory_reports_server_errors(mocker):
    err = ServerRequestError("'nope' is not a directory")
    _mock_interface(mocker, get_datasets_in_directory=mocker.MagicMock(side_effect=err))

    options, status, committed = use_directory(1, {"path": "nope"}, True)

    assert options is no_update
    assert committed is no_update
    assert "not a directory" in status.children


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

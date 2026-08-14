import json

import pytest
from dash import html, no_update
from dash._callback_context import context_value
from dash._utils import AttributeDict

# the components package re-exports the directory_selector *function* under the
# module's own name, so these have to come off the module path directly.
from spectra_inspector.components.directory_selector import (
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

    label, entries, up_disabled, status = show_directory_listing({"path": "session-a"})

    assert label == "<data root>/session-a"
    assert [e.id["name"] for e in entries] == ["session-a/nested"]
    assert [e.children for e in entries] == ["nested"]
    assert up_disabled is False
    assert "1 dataset directly" in status.children


def test_show_directory_listing_uses_the_matched_index(mocker):
    # the picker is index 1 on the inspector page, and the clickable entries
    # have to carry that index or MATCH will never pair them with the store
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=_LISTING))
    _set_outputs_for_index(1)

    _, entries, _, _ = show_directory_listing({"path": "session-a"})

    assert [e.id["index"] for e in entries] == [1]


def test_show_directory_listing_with_no_subdirectories(mocker):
    leaf = directoryListing(path="a", name="a", parent_path="", dataset_count=3)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=leaf))
    _set_outputs_for_index(0)

    _, entries, up_disabled, status = show_directory_listing({"path": "a"})

    # a placeholder row, and crucially nothing carrying a clickable id
    assert len(entries) == 1
    assert entries[0].disabled is True
    assert not hasattr(entries[0], "name")
    assert up_disabled is False
    assert "3 datasets directly" in status.children


def test_show_directory_listing_at_the_data_root(mocker):
    root = directoryListing(path="", name="root", parent_path=None, dataset_count=0)
    _mock_interface(mocker, browse_directory=mocker.MagicMock(return_value=root))
    _set_outputs_for_index(0)

    label, entries, up_disabled, status = show_directory_listing({"path": ""})

    assert label == "<data root>"
    assert len(entries) == 1
    assert entries[0].disabled is True
    assert up_disabled is True
    assert "0 datasets directly" in status.children


def test_show_directory_listing_reports_server_errors(mocker):
    err = ServerRequestError("directory browsing requires DESKTOP_MODE")
    _mock_interface(mocker, browse_directory=mocker.MagicMock(side_effect=err))
    _set_outputs_for_index(0)

    label, entries, up_disabled, status = show_directory_listing({"path": "a"})

    assert label == "<data root>/a"
    assert entries == []
    assert up_disabled is False
    assert "DESKTOP_MODE" in status.children


def test_show_directory_listing_without_a_backend(mocker):
    sisi = mocker.MagicMock()
    sisi.connected = False
    mocker.patch(_INTERFACE_PATH, mocker.MagicMock(return_value=sisi))

    _set_outputs_for_index(0)

    _, entries, _, status = show_directory_listing({"path": ""})

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
        "available_files": ["C-1", "C-2"],
        "sample_metadata": {"records": [], "map_samples": {}},
    }


def test_use_directory_passes_the_recursive_flag(mocker):
    available = AvailableDatasets(available_files=["C-1"])
    sisi = _mock_interface(
        mocker, get_datasets_in_directory=mocker.MagicMock(return_value=available)
    )

    _, status, _ = use_directory(1, {"path": "session-a"}, False)

    sisi.get_datasets_in_directory.assert_called_once_with("session-a", recursive=False)
    assert "Loaded 1 dataset " in status.children


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

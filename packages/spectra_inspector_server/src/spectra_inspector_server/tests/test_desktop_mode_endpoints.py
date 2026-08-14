from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spectra_inspector_server._database.on_disk_db import get_expected_files
from spectra_inspector_server.dependencies import get_database_session, get_settings
from spectra_inspector_server.main import _valid_sample_name, app
from spectra_inspector_server.model import AvailableDatasets, directoryListing
from spectra_inspector_server.settings import ENV_PREFIX


def _write_edax_set(directory: Path, basename: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sample_file in get_expected_files(directory / (basename + ".spd")).values():
        sample_file.write_text(f"writing to {sample_file}")


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "C-1")
    _write_edax_set(root / "session-a" / "nested", "C-2")
    _write_edax_set(root / "session-b", "C-3")
    return root


@pytest.fixture
def _clear_dependency_caches() -> Generator[None, None, None]:
    get_settings.cache_clear()
    get_database_session.cache_clear()
    yield
    get_settings.cache_clear()
    get_database_session.cache_clear()


def _client(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    desktop_mode: bool,
    max_datasets: int | None = None,
) -> TestClient:
    monkeypatch.setenv(f"{ENV_PREFIX}DATA_ROOT", str(data_root))
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", str(desktop_mode).lower())
    if max_datasets is not None:
        monkeypatch.setenv(f"{ENV_PREFIX}MAX_DATASETS", str(max_datasets))
    return TestClient(app)


@pytest.fixture
def desktop_client(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clear_dependency_caches: None,
) -> Generator[TestClient, None, None]:
    with _client(data_root, monkeypatch, desktop_mode=True) as client:
        yield client


@pytest.fixture
def server_client(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clear_dependency_caches: None,
) -> Generator[TestClient, None, None]:
    with _client(data_root, monkeypatch, desktop_mode=False) as client:
        yield client


@pytest.fixture
def capped_desktop_client(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clear_dependency_caches: None,
) -> Generator[TestClient, None, None]:
    with _client(data_root, monkeypatch, desktop_mode=True, max_datasets=2) as client:
        yield client


@pytest.fixture
def capped_server_client(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clear_dependency_caches: None,
) -> Generator[TestClient, None, None]:
    with _client(data_root, monkeypatch, desktop_mode=False, max_datasets=2) as client:
        yield client


def test_desktop_mode_defers_the_scan(desktop_client: TestClient) -> None:
    response = desktop_client.get("/available-datasets")
    assert response.status_code == 200

    datasets = AvailableDatasets(**response.json())
    assert datasets.available_files == []
    assert datasets.directory is None


def test_server_mode_scans_at_startup(server_client: TestClient) -> None:
    response = server_client.get("/available-datasets")
    assert response.status_code == 200

    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2", "C-3"}


def test_info_reports_desktop_mode(desktop_client: TestClient) -> None:
    assert desktop_client.get("/info").json()["desktop_mode"] is True


def test_info_reports_server_mode(server_client: TestClient) -> None:
    assert server_client.get("/info").json()["desktop_mode"] is False


@pytest.mark.parametrize("endpoint", ["/browse-directory", "/datasets-in-directory"])
def test_browsing_denied_outside_desktop_mode(
    server_client: TestClient, endpoint: str
) -> None:
    response = server_client.get(endpoint)
    assert response.status_code == 403
    assert "DESKTOP_MODE" in response.json()["detail"]


def test_browse_data_root(desktop_client: TestClient) -> None:
    response = desktop_client.get("/browse-directory")
    assert response.status_code == 200

    listing = directoryListing(**response.json())
    assert listing.path == ""
    assert listing.parent_path is None
    assert [d.name for d in listing.directories] == ["session-a", "session-b"]


def test_browse_subdirectory(desktop_client: TestClient) -> None:
    response = desktop_client.get("/browse-directory", params={"path": "session-a"})
    assert response.status_code == 200

    listing = directoryListing(**response.json())
    assert listing.path == "session-a"
    assert listing.parent_path == ""
    assert listing.dataset_count == 1
    assert [d.path for d in listing.directories] == ["session-a/nested"]


@pytest.mark.parametrize("path", ["..", "/etc", "session-a/../.."])
def test_browse_outside_data_root_is_forbidden(
    desktop_client: TestClient, path: str
) -> None:
    response = desktop_client.get("/browse-directory", params={"path": path})
    assert response.status_code == 403


def test_browse_missing_directory(desktop_client: TestClient) -> None:
    response = desktop_client.get("/browse-directory", params={"path": "nope"})
    assert response.status_code == 404


def test_datasets_in_directory_sets_the_working_set(desktop_client: TestClient) -> None:
    response = desktop_client.get(
        "/datasets-in-directory", params={"path": "session-a"}
    )
    assert response.status_code == 200

    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2"}
    assert datasets.directory == "session-a"

    # the working set persists for later requests
    listed = AvailableDatasets(**desktop_client.get("/available-datasets").json())
    assert set(listed.available_files) == {"C-1", "C-2"}
    assert listed.directory == "session-a"


def test_datasets_in_directory_non_recursive(desktop_client: TestClient) -> None:
    response = desktop_client.get(
        "/datasets-in-directory",
        params={"path": "session-a", "recursive": False},
    )
    assert response.status_code == 200
    assert set(AvailableDatasets(**response.json()).available_files) == {"C-1"}


def test_datasets_in_directory_replaces_previous_selection(
    desktop_client: TestClient,
) -> None:
    desktop_client.get("/datasets-in-directory", params={"path": "session-a"})
    response = desktop_client.get(
        "/datasets-in-directory", params={"path": "session-b"}
    )

    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-3"}


def test_datasets_in_data_root(desktop_client: TestClient) -> None:
    response = desktop_client.get("/datasets-in-directory")
    assert response.status_code == 200

    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2", "C-3"}
    assert datasets.directory == ""


def test_max_datasets_truncates_the_scan(capped_desktop_client: TestClient) -> None:
    response = capped_desktop_client.get("/datasets-in-directory")
    assert response.status_code == 200

    # the whole data root holds three sets; the scan stops after two, taking
    # them in traversal order (session-a, then its nested subdirectory).
    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2"}
    assert datasets.truncated is True


def test_max_datasets_applies_to_every_selection(
    capped_desktop_client: TestClient,
) -> None:
    # a directory under the cap is unaffected, and reports as much
    response = capped_desktop_client.get(
        "/datasets-in-directory", params={"path": "session-b"}
    )
    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-3"}
    assert datasets.truncated is False

    # and the cap still applies to the next selection rather than being
    # consumed by the first one
    response = capped_desktop_client.get("/datasets-in-directory")
    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2"}
    assert datasets.truncated is True


def test_truncation_flag_persists_on_later_listings(
    capped_desktop_client: TestClient,
) -> None:
    # /available-datasets serves the working set the last scan produced, so it
    # has to keep flagging that the set is partial
    capped_desktop_client.get("/datasets-in-directory")

    datasets = AvailableDatasets(
        **capped_desktop_client.get("/available-datasets").json()
    )
    assert set(datasets.available_files) == {"C-1", "C-2"}
    assert datasets.truncated is True


def test_max_datasets_ignored_outside_desktop_mode(
    capped_server_client: TestClient,
) -> None:
    datasets = AvailableDatasets(
        **capped_server_client.get("/available-datasets").json()
    )
    assert set(datasets.available_files) == {"C-1", "C-2", "C-3"}
    assert datasets.truncated is False


def test_uncapped_scans_are_never_truncated(desktop_client: TestClient) -> None:
    response = desktop_client.get("/datasets-in-directory")
    assert AvailableDatasets(**response.json()).truncated is False


@pytest.mark.parametrize("path", ["..", "/etc"])
def test_datasets_outside_data_root_is_forbidden(
    desktop_client: TestClient, path: str
) -> None:
    response = desktop_client.get("/datasets-in-directory", params={"path": path})
    assert response.status_code == 403


def test_datasets_in_missing_directory(desktop_client: TestClient) -> None:
    response = desktop_client.get("/datasets-in-directory", params={"path": "nope"})
    assert response.status_code == 404


def test_working_directory_param_syncs_a_worker_that_missed_the_selection(
    desktop_client: TestClient,
) -> None:
    """Behind several uvicorn workers only one of them served
    /datasets-in-directory. This client stands in for one of the others: it has
    never scanned anything, and the directory carried on the request is what
    lets it catch up."""

    cold = AvailableDatasets(**desktop_client.get("/available-datasets").json())
    assert cold.available_files == []

    response = desktop_client.get(
        "/available-datasets", params={"working_directory": "session-a"}
    )
    assert response.status_code == 200

    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2"}
    assert datasets.directory == "session-a"


def test_working_directory_param_honours_the_recursive_flag(
    desktop_client: TestClient,
) -> None:
    response = desktop_client.get(
        "/available-datasets",
        params={
            "working_directory": "session-a",
            "working_directory_recursive": False,
        },
    )
    assert set(AvailableDatasets(**response.json()).available_files) == {"C-1"}


def test_empty_working_directory_means_the_data_root(
    desktop_client: TestClient,
) -> None:
    # "" is a real selection, so it must sync rather than be read as "unset"
    desktop_client.get("/datasets-in-directory", params={"path": "session-b"})

    response = desktop_client.get(
        "/available-datasets", params={"working_directory": ""}
    )
    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2", "C-3"}
    assert datasets.directory == ""


def test_no_working_directory_param_leaves_the_selection_alone(
    desktop_client: TestClient,
) -> None:
    desktop_client.get("/datasets-in-directory", params={"path": "session-b"})

    datasets = AvailableDatasets(**desktop_client.get("/available-datasets").json())
    assert set(datasets.available_files) == {"C-3"}
    assert datasets.directory == "session-b"


def test_matching_working_directory_does_not_rescan(
    desktop_client: TestClient,
) -> None:
    desktop_client.get("/datasets-in-directory", params={"path": "session-a"})
    ph = desktop_client.app.state.ph  # type:ignore[attr-defined]
    before = ph.database.available_maps

    desktop_client.get("/available-datasets", params={"working_directory": "session-a"})

    # same directory, so the database object is left untouched rather than
    # rebuilt on every single request
    assert ph.database.available_maps is before


def test_working_directory_is_ignored_outside_desktop_mode(
    server_client: TestClient,
) -> None:
    # a full-scan server shares one database across workers already, and must
    # not let a client narrow it
    response = server_client.get(
        "/available-datasets", params={"working_directory": "session-a"}
    )
    assert response.status_code == 200
    assert set(AvailableDatasets(**response.json()).available_files) == {
        "C-1",
        "C-2",
        "C-3",
    }


@pytest.mark.parametrize("path", ["..", "/etc"])
def test_working_directory_outside_data_root_is_forbidden(
    desktop_client: TestClient, path: str
) -> None:
    response = desktop_client.get(
        "/available-datasets", params={"working_directory": path}
    )
    assert response.status_code == 403


def test_working_directory_syncs_the_data_endpoints_too(
    desktop_client: TestClient,
) -> None:
    """The dataset list is not the only thing gated on the per-worker database;
    every data endpoint checks the sample name against it."""

    ph = desktop_client.app.state.ph  # type:ignore[attr-defined]
    assert _valid_sample_name("C-3", ph) is False

    # ask for a name that is not there either way, so the sync is all that
    # happens -- these fixtures' EDAX files are stubs that cannot be loaded
    response = desktop_client.get(
        "/image-metadata",
        params={"sample_name": "not-a-sample", "working_directory": "session-b"},
    )
    assert response.status_code == 404

    # the directory still landed, so the samples in it are now addressable
    assert _valid_sample_name("C-3", ph) is True
    assert ph.database.working_directory.name == "session-b"


def test_selected_datasets_become_valid_sample_names(
    desktop_client: TestClient,
) -> None:
    # before selecting a directory nothing is a valid sample name
    response = desktop_client.get("/image-metadata", params={"sample_name": "C-3"})
    assert response.status_code == 404

    desktop_client.get("/datasets-in-directory", params={"path": "session-b"})

    # the data endpoints share the app-state path handler, so the newly scanned
    # datasets are now loadable by name.
    ph = desktop_client.app.state.ph  # type:ignore[attr-defined]
    assert _valid_sample_name("C-3", ph) is True
    assert _valid_sample_name("C-1", ph) is False

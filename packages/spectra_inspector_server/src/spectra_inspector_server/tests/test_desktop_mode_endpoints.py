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
    data_root: Path, monkeypatch: pytest.MonkeyPatch, desktop_mode: bool
) -> TestClient:
    monkeypatch.setenv(f"{ENV_PREFIX}DATA_ROOT", str(data_root))
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", str(desktop_mode).lower())
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


@pytest.mark.parametrize("path", ["..", "/etc"])
def test_datasets_outside_data_root_is_forbidden(
    desktop_client: TestClient, path: str
) -> None:
    response = desktop_client.get("/datasets-in-directory", params={"path": path})
    assert response.status_code == 403


def test_datasets_in_missing_directory(desktop_client: TestClient) -> None:
    response = desktop_client.get("/datasets-in-directory", params={"path": "nope"})
    assert response.status_code == 404


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

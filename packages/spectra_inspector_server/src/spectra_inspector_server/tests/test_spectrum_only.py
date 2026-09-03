"""Standalone ``.spc`` spectra (issue #115).

A map's file set always includes an ``.spc``, and the users also have plenty of
``.spc`` files with no map behind them. Both are listed as spectra, and the
``spectrum_only`` request parameter says which of the two things a sample name
refers to.

No real EDAX data is checked in: the scanning tests use empty stub files, and
the loading tests write a synthetic ``.spc`` with rsciio's own header layout
(``_testing.write_mock_spc``).
"""

import logging
from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spectra_inspector_server._database.on_disk_db import get_expected_files
from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import (
    _on_disc_mock,
    createEDAXSpectrumMock,
    write_mock_spc,
)
from spectra_inspector_server.dependencies import get_database_session, get_settings
from spectra_inspector_server.main import _valid_sample_name, app
from spectra_inspector_server.model import (
    AvailableDatasets,
    CombinedMetadata,
    EDAX_raw_ds,
    MetadataModel,
    Spectrum1dDict,
    directoryListing,
)
from spectra_inspector_server.processor.file_loaders import load_edax_spc
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler
from spectra_inspector_server.settings import ENV_PREFIX


def _write_edax_set(directory: Path, basename: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sample_file in get_expected_files(directory / (basename + ".spd")).values():
        sample_file.write_text(f"writing to {sample_file}")


def _write_standalone_spc(directory: Path, basename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    spc = directory / f"{basename}.spc"
    spc.write_text(f"writing to {spc}")
    return spc


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "C-1")
    _write_edax_set(root / "session-a" / "nested", "C-2")
    _write_standalone_spc(root / "session-a", "S-1")
    _write_standalone_spc(root / "session-b", "S-2")
    return root


# ---------------------------------------------------------------------------
# scanning


def test_scan_lists_every_spc_as_a_spectrum(data_root: Path) -> None:
    ph = EDAXPathHandler(data_root, init_db=True)

    # a map needs its whole file set, a lone .spc is not one
    assert set(ph.database.available_maps) == {"C-1", "C-2"}
    # but every .spc is a spectrum, whether or not it belongs to a set
    assert set(ph.database.available_spectra) == {"C-1", "C-2", "S-1", "S-2"}
    assert ph.database.available_spectra["S-1"].name == "S-1.spc"
    assert ph.database.available_spectra["C-1"] == ph.database.available_maps["C-1"].spc


def test_spectra_join_the_sample_lookup(data_root: Path) -> None:
    ph = EDAXPathHandler(data_root, init_db=True)
    assert set(ph.database.available_samples) == {"C-1", "C-2", "S-1", "S-2"}


def test_duplicate_spectrum_warns_and_skips(
    data_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_standalone_spc(data_root / "session-b", "S-1")

    with caplog.at_level(logging.WARNING):
        ph = EDAXPathHandler(data_root, init_db=True)

    assert set(ph.database.available_spectra) == {"C-1", "C-2", "S-1", "S-2"}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Duplicate spectrum name" in warnings[0]


def test_working_directory_scopes_the_spectra(data_root: Path) -> None:
    ph = EDAXPathHandler(data_root, init_db=False)
    assert ph.database.available_spectra == {}

    ph.set_working_directory(data_root / "session-b")
    assert set(ph.database.available_spectra) == {"S-2"}
    assert ph.database.available_maps == {}

    ph.set_working_directory(data_root / "session-a", recursive=False)
    assert set(ph.database.available_spectra) == {"C-1", "S-1"}


def test_add_spectrum_return_value(tmp_path: Path) -> None:
    ph = EDAXPathHandler(tmp_path, init_db=False)
    spc = tmp_path / "S-1.spc"
    assert ph.database.add_spectrum("S-1", spc) is True
    assert ph.database.add_spectrum("S-1", spc) is False
    assert len(ph.database.available_spectra) == 1


# ---------------------------------------------------------------------------
# loading


def test_synthetic_spc_round_trips_through_rsciio(tmp_path: Path) -> None:
    spc = tmp_path / "S-1.spc"
    written = write_mock_spc(spc, ev_per_channel=5, start_energy=-0.1)

    ds = load_edax_spc(spc)
    assert isinstance(ds, EDAX_raw_ds)
    assert ds.data is not None
    assert ds.data.shape == (4096,)
    assert np.array_equal(ds.data, written)

    (energy,) = ds.axes
    assert energy.index_in_array == 0
    assert energy.units == "keV"
    assert energy.scale == pytest.approx(0.005)
    assert energy.offset == pytest.approx(-0.1)
    assert ds.axes_by_index == {0: energy}

    refined = ds.refined_metadata
    assert refined.General.title == "EDS Spectrum"
    assert refined.Acquisition_instrument.SEM.beam_energy == 15.0
    assert set(refined.Sample.elements) == {
        "O",
        "Na",
        "Mg",
        "Al",
        "Si",
        "K",
        "Ca",
        "Fe",
    }


@pytest.fixture
def ops_with_spectrum(tmp_path: Path) -> tuple[OperationEDAXStateHandler, np.ndarray]:
    root = tmp_path / "data_root"
    root.mkdir()
    written = write_mock_spc(root / "S-1.spc")
    ph = EDAXPathHandler(root, init_db=True)
    return OperationEDAXStateHandler(ph), written


def test_get_spectrum_reads_the_spc(
    ops_with_spectrum: tuple[OperationEDAXStateHandler, np.ndarray],
) -> None:
    ops, written = ops_with_spectrum

    spectrum = ops.get_spectrum("S-1", spectrum_only=True)
    assert np.array_equal(spectrum.intensity, written)
    assert np.array_equal(spectrum.energy, np.arange(4096))
    assert spectrum.energy_min == pytest.approx(0.0)
    assert spectrum.energy_max == pytest.approx(40.96)
    assert spectrum.metadata is not None
    assert spectrum.metadata["General"]["title"] == "EDS Spectrum"
    assert spectrum.original_metadata is not None
    assert spectrum.original_metadata["spc_header"]["numPts"] == 4096

    # 10 eV channels span the calibration windows, so weights are available
    weights = spectrum.get_weights()
    assert weights is not None
    assert weights.total_count == float(written.sum())


def test_get_spectrum_channel_range(
    ops_with_spectrum: tuple[OperationEDAXStateHandler, np.ndarray],
) -> None:
    ops, written = ops_with_spectrum
    spectrum = ops.get_spectrum("S-1", channel_range=(100, 200), spectrum_only=True)
    assert np.array_equal(spectrum.intensity, written[100:200])
    assert np.array_equal(spectrum.energy, np.arange(100, 200))
    assert spectrum.energy_min == pytest.approx(1.0)
    assert spectrum.energy_max == pytest.approx(2.0)


def test_spectrum_metadata_endpoints_describe_a_1d_dataset(
    ops_with_spectrum: tuple[OperationEDAXStateHandler, np.ndarray],
) -> None:
    ops, _ = ops_with_spectrum

    combined = ops.get_combined_metadata("S-1", spectrum_only=True)
    assert combined.data_shape == (4096,)
    assert list(combined.axes_by_index) == [0]
    assert combined.axes_by_index[0].name == "Energy"

    assert ops.get_refined_metadata("S-1", spectrum_only=True).General.title == (
        "EDS Spectrum"
    )


def test_a_lone_spc_is_not_a_map(
    ops_with_spectrum: tuple[OperationEDAXStateHandler, np.ndarray],
) -> None:
    ops, _ = ops_with_spectrum
    with pytest.raises(KeyError):
        ops.get_spectrum("S-1")
    with pytest.raises(KeyError):
        ops.get_combined_metadata("S-1")
    with pytest.raises(KeyError):
        ops.get_single_image("S-1", channel_index=0)


def test_spectrum_mock_shape() -> None:
    ds = createEDAXSpectrumMock(n_channels=64)
    assert ds.data is not None
    assert ds.data.shape == (64,)
    assert ds.axes_by_index[0].size == 64
    assert ds.refined_metadata.General.title == "EDS Spectrum"


def test_mock_names_by_kind() -> None:
    # every mock map has a spectrum, and one spectrum has no map
    for name in _on_disc_mock.filenames:
        assert _on_disc_mock.is_mock(name)
        assert _on_disc_mock.is_mock(name, spectrum_only=True)
    for name in _on_disc_mock.spectrum_only_filenames:
        assert not _on_disc_mock.is_mock(name)
        assert _on_disc_mock.is_mock(name, spectrum_only=True)
        assert _on_disc_mock.load(name, spectrum_only=True).data is not None
        with pytest.raises(ValueError, match="not a fake file"):
            _on_disc_mock.load(name)


# ---------------------------------------------------------------------------
# endpoints, against the mocks


@pytest.fixture
def app_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


SPECTRUM_ONLY_NAME = _on_disc_mock.spectrum_only_filenames[0]
MAP_NAME = _on_disc_mock.filenames[0]


def test_available_datasets_carries_spectra(app_client: TestClient) -> None:
    response = app_client.get("/available-datasets")
    assert response.status_code == 200
    assert "available_spectra" in response.json()
    AvailableDatasets(**response.json())


def test_image_spectrum_spectrum_only(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-spectrum",
        params={"sample_name": SPECTRUM_ONLY_NAME, "spectrum_only": True},
    )
    assert response.status_code == 200
    spectrum = Spectrum1dDict(**response.json())
    assert len(spectrum.intensity) == len(spectrum.energy) == 4096
    assert spectrum.energy_max == pytest.approx(40.96)
    assert spectrum.weights is not None
    assert spectrum.metadata is not None
    assert spectrum.metadata["General"]["title"] == "EDS Spectrum"


def test_image_spectrum_spectrum_only_channel_range(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-spectrum",
        params={
            "sample_name": SPECTRUM_ONLY_NAME,
            "spectrum_only": True,
            "channel_0": 10,
            "channel_1": 20,
            "include_weights": False,
        },
    )
    assert response.status_code == 200
    spectrum = Spectrum1dDict(**response.json())
    assert spectrum.energy == list(range(10, 20))
    assert spectrum.weights is None


def test_a_map_sample_is_also_a_spectrum(app_client: TestClient) -> None:
    for spectrum_only in (False, True):
        response = app_client.get(
            "/image-spectrum",
            params={
                "sample_name": MAP_NAME,
                "spectrum_only": spectrum_only,
                "include_weights": False,
            },
        )
        assert response.status_code == 200, spectrum_only


def test_spectrum_only_names_are_not_maps(app_client: TestClient) -> None:
    # without the flag the name is looked up among the maps, and it is not one
    response = app_client.get(
        "/image-spectrum", params={"sample_name": SPECTRUM_ONLY_NAME}
    )
    assert response.status_code == 404

    # and the image endpoints only ever serve maps
    response = app_client.get(
        "/image-data", params={"sample_name": SPECTRUM_ONLY_NAME, "channel_index": 0}
    )
    assert response.status_code == 404


def test_metadata_endpoints_spectrum_only(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-metadata",
        params={"sample_name": SPECTRUM_ONLY_NAME, "spectrum_only": True},
    )
    assert response.status_code == 200
    assert MetadataModel(**response.json()).General.title == "EDS Spectrum"

    response = app_client.get(
        "/image-metadata-combined",
        params={"sample_name": SPECTRUM_ONLY_NAME, "spectrum_only": True},
    )
    assert response.status_code == 200
    combined = CombinedMetadata(**response.json())
    assert len(combined.data_shape) == 1
    assert combined.axes_by_index[0].size == combined.data_shape[0]

    response = app_client.get(
        "/image-metadata", params={"sample_name": SPECTRUM_ONLY_NAME}
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# endpoints, against a scanned data root


@pytest.fixture
def _clear_dependency_caches() -> Generator[None, None, None]:
    get_settings.cache_clear()
    get_database_session.cache_clear()
    yield
    get_settings.cache_clear()
    get_database_session.cache_clear()


@pytest.fixture
def desktop_client(
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clear_dependency_caches: None,
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv(f"{ENV_PREFIX}DATA_ROOT", str(data_root))
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "true")
    with TestClient(app) as client:
        yield client


def test_browse_directory_counts_spectra(desktop_client: TestClient) -> None:
    response = desktop_client.get("/browse-directory", params={"path": "session-a"})
    assert response.status_code == 200
    listing = directoryListing(**response.json())
    assert listing.dataset_count == 1
    # the set's own .spc plus the standalone one
    assert listing.spectrum_count == 2

    response = desktop_client.get("/browse-directory", params={"path": "session-b"})
    listing = directoryListing(**response.json())
    assert listing.dataset_count == 0
    assert listing.spectrum_count == 1


def test_datasets_in_directory_lists_spectra(desktop_client: TestClient) -> None:
    response = desktop_client.get(
        "/datasets-in-directory", params={"path": "session-a"}
    )
    assert response.status_code == 200
    datasets = AvailableDatasets(**response.json())
    assert set(datasets.available_files) == {"C-1", "C-2"}
    assert set(datasets.available_spectra) == {"C-1", "C-2", "S-1"}
    assert datasets.sample_metadata is None

    ph = desktop_client.app.state.ph  # type:ignore[attr-defined]
    assert _valid_sample_name("S-1", ph) is False
    assert _valid_sample_name("S-1", ph, spectrum_only=True) is True
    assert _valid_sample_name("C-1", ph, spectrum_only=True) is True

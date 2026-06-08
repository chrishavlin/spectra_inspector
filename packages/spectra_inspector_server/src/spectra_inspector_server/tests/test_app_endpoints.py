from collections.abc import Generator

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spectra_inspector_server._testing import _on_disc_mock
from spectra_inspector_server.main import app
from spectra_inspector_server.model import (
    CombinedMetadata,
    MetadataModel,
    Spectrum1dDict,
    raveledImage,
)

_endpoints_keys = [
    ("info", ["app_name", "spectra_inspector_data_root"]),
    ("available-datasets", ["available_files"]),
]


@pytest.fixture
def app_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(("endpoint", "response_keys"), _endpoints_keys)
def test_endpoint_responses(
    endpoint: str, response_keys: list[str] | None, app_client: TestClient
) -> None:
    response = app_client.get(f"/{endpoint}")
    assert response.status_code == 200

    if response_keys:
        jdict = response.json()
        all(ky in jdict for ky in response_keys)


def test_image_metadata(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-metadata", params={"sample_name": _on_disc_mock.filenames[0]}
    )
    assert response.status_code == 200
    mm = MetadataModel(**response.json())
    assert mm.General.title == "EDS Spectrum Image"


def test_image_combined_metadata(app_client: TestClient) -> None:

    response = app_client.get(
        "/image-metadata-combined", params={"sample_name": _on_disc_mock.filenames[0]}
    )
    assert response.status_code == 200
    mm = CombinedMetadata(**response.json())

    assert mm.metadata.General.title == "EDS Spectrum Image"

    assert len(mm.data_shape) == 3
    for indx in range(3):
        assert mm.axes_by_index[indx].size == mm.data_shape[indx]


def test_image_spectrum(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-spectrum", params={"sample_name": _on_disc_mock.filenames[0]}
    )
    assert response.status_code == 200
    spectrum = Spectrum1dDict(**response.json())
    assert np.all(np.isreal(spectrum.energy))
    assert np.all(np.isreal(spectrum.intensity))


def test_image_data(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-data",
        params={"sample_name": _on_disc_mock.filenames[0], "channel_index": 2},
    )
    assert response.status_code == 200
    spectrum = raveledImage(**response.json())
    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))


def test_image_data_subset(app_client: TestClient) -> None:

    response = app_client.get(
        "/image-data",
        params={
            "sample_name": _on_disc_mock.filenames[0],
            "channel_index": 2,
            "index0_0": 2,
            "index0_1": 5,
            "index1_0": 3,
            "index1_1": 8,
        },
    )
    assert response.status_code == 200
    spectrum = raveledImage(**response.json())
    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))

    assert spectrum.shape == (3, 5)


def test_image_data_summed(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-data-summed",
        params={
            "sample_name": _on_disc_mock.filenames[0],
            "channel_0": 0,
            "channel_1": 4,
        },
    )
    assert response.status_code == 200
    spectrum = raveledImage(**response.json())
    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))


def test_image_data_summed_subset(app_client: TestClient) -> None:
    response = app_client.get(
        "/image-data-summed",
        params={
            "sample_name": _on_disc_mock.filenames[0],
            "channel_0": 0,
            "channel_1": 4,
            "index0_0": 2,
            "index0_1": 5,
            "index1_0": 3,
            "index1_1": 8,
        },
    )
    assert response.status_code == 200
    spectrum = raveledImage(**response.json())
    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))

    assert spectrum.shape == (3, 5)

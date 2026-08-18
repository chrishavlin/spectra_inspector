# import requests

import numpy as np
import pytest

from spectra_inspector.utilities.interface import (
    ServerRequestError,
    SpectraInspectorServerInterface,
)
from spectra_inspector.utilities.model import Spectrum1dDict


def test_init():
    host = "123.456.789"
    port = 999
    protocol = "https"
    sisi = SpectraInspectorServerInterface(host=host, port=port, protocol=protocol)

    endpoint = "not_an_endpoint"
    expected_base_uri = f"{protocol}://{host}:{port}"
    assert sisi.uri == expected_base_uri
    uri = sisi._get_endpoint(endpoint)
    assert uri == f"{expected_base_uri}/{endpoint}"
    assert sisi.connected is False


def test_available_datasets(mocker):

    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"available_files": ["f1", "f2", "f3"]}
    mocker.patch("requests.Session.get", return_value=mock_response)

    sisi = SpectraInspectorServerInterface()
    assert sisi.connected
    available = sisi.get_available_datasets()
    assert len(available.available_files) == 3


def test_get_image_spectrum(mocker):

    mock_response = mocker.Mock()
    mock_response.status_code = 200

    expected_response = Spectrum1dDict(
        energy=list(range(10)),
        intensity=list(range(10)),
        energy_min=0,
        energy_max=1,
    )

    mock_response.json.return_value = expected_response.model_dump()
    mocker.patch("requests.Session.get", return_value=mock_response)

    sisi = SpectraInspectorServerInterface()
    assert sisi.connected
    spect = sisi.get_image_spectrum(
        "sample_name",
    )
    assert np.all(np.array(spect.energy) == np.array(expected_response.energy))
    assert np.all(np.array(spect.intensity) == np.array(expected_response.intensity))
    assert spect.energy_max == expected_response.energy_max
    assert spect.energy_min == expected_response.energy_min


def _mock_get(mocker, payload: dict, status_code: int = 200):
    mock_response = mocker.Mock()
    mock_response.status_code = status_code
    mock_response.json.return_value = payload
    return mocker.patch("requests.Session.get", return_value=mock_response)


def test_browse_directory(mocker):
    payload = {
        "path": "session-a",
        "name": "session-a",
        "parent_path": "",
        "directories": [{"name": "nested", "path": "session-a/nested"}],
        "dataset_count": 2,
    }
    mock_get = _mock_get(mocker, payload)

    sisi = SpectraInspectorServerInterface()
    listing = sisi.browse_directory("session-a")

    assert mock_get.call_args.kwargs["params"] == {"path": "session-a"}
    assert listing.path == "session-a"
    assert listing.parent_path == ""
    assert listing.dataset_count == 2
    assert listing.directories[0].name == "nested"
    assert listing.directories[0].path == "session-a/nested"


def test_get_datasets_in_directory(mocker):
    payload = {
        "available_files": ["C-1", "C-2"],
        "sample_metadata": None,
        "directory": "session-a",
    }
    mock_get = _mock_get(mocker, payload)

    sisi = SpectraInspectorServerInterface()
    available = sisi.get_datasets_in_directory("session-a", recursive=False)

    assert mock_get.call_args.kwargs["params"] == {
        "path": "session-a",
        "recursive": False,
    }
    assert available.available_files == ["C-1", "C-2"]
    assert available.directory == "session-a"


def test_browse_directory_raises_on_server_error(mocker):
    _mock_get(mocker, {"detail": "'..' is outside of the data root"}, status_code=403)

    sisi = SpectraInspectorServerInterface()
    with pytest.raises(ServerRequestError, match="outside of the data root"):
        sisi.browse_directory("..")


def test_datasets_in_directory_raises_on_server_error(mocker):
    _mock_get(mocker, {"detail": "'nope' is not a directory"}, status_code=404)

    sisi = SpectraInspectorServerInterface()
    with pytest.raises(ServerRequestError, match="not a directory"):
        sisi.get_datasets_in_directory("nope")


def test_server_error_without_a_detail_payload(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 500
    mock_response.json.side_effect = ValueError("not json")
    mocker.patch("requests.Session.get", return_value=mock_response)

    sisi = SpectraInspectorServerInterface()
    with pytest.raises(ServerRequestError, match="status 500"):
        sisi.browse_directory()

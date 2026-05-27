# import requests
from dataclasses import asdict

import numpy as np

from spectra_inspector.server.model import Spectrum1dDict
from spectra_inspector.utilities.external_interface import (
    SpectraInspectorServerInterface,
)


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
    mocker.patch("requests.get", return_value=mock_response)

    sisi = SpectraInspectorServerInterface()
    assert sisi.connected
    available = sisi.get_available_datasets()
    assert len(available.available_files) == 3


def test_get_image_spectrum(mocker):

    mock_response = mocker.Mock()
    mock_response.status_code = 200

    expected_response = Spectrum1dDict(list(range(10)), list(range(10)), 0, 1)

    mock_response.json.return_value = asdict(expected_response)
    mocker.patch("requests.get", return_value=mock_response)

    sisi = SpectraInspectorServerInterface()
    assert sisi.connected
    spect = sisi.get_image_spectrum(
        "sample_name",
    )
    assert np.all(np.array(spect.energy) == np.array(expected_response.energy))
    assert np.all(np.array(spect.intensity) == np.array(expected_response.intensity))
    assert spect.energy_max == expected_response.energy_max
    assert spect.energy_min == expected_response.energy_min

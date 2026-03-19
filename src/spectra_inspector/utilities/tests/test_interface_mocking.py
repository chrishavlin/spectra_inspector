# import requests
from dataclasses import asdict

import numpy as np

from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import Spectrum1dDict


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

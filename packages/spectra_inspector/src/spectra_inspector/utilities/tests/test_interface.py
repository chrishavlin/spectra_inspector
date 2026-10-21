from email.utils import format_datetime

import numpy as np
import pytest
import requests

from spectra_inspector.utilities import interface
from spectra_inspector.utilities.interface import (
    ServerRequestError,
    SpectraInspectorServerInterface,
    loadFailure,
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
    with pytest.raises(ServerRequestError, match="status 500") as excinfo:
        sisi.browse_directory()
    assert excinfo.value.status_code == 500


def _response(mocker, status_code: int, payload: dict, headers: dict | None = None):
    response = mocker.Mock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = payload
    return response


def _busy(mocker, retry_after: str = "3"):
    return _response(
        mocker, 503, {"detail": "the server is busy"}, {"Retry-After": retry_after}
    )


def test_a_503_is_retried_once_after_the_servers_retry_after(mocker):
    ok = _response(mocker, 200, {"available_files": ["f1"]})
    get = mocker.patch("requests.Session.get", side_effect=[_busy(mocker), ok])
    sleep = mocker.patch.object(interface, "_sleep")

    sisi = SpectraInspectorServerInterface()
    assert sisi.get_available_datasets().available_files == ["f1"]
    assert get.call_count == 2
    sleep.assert_called_once_with(3.0)


def test_a_second_503_is_raised_with_its_status(mocker):
    get = mocker.patch("requests.Session.get", return_value=_busy(mocker))
    mocker.patch.object(interface, "_sleep")

    sisi = SpectraInspectorServerInterface()
    with pytest.raises(ServerRequestError, match="busy") as excinfo:
        sisi.get_image_spectrum("a-sample")
    # exactly one retry: anything more is the user's call
    assert get.call_count == 2
    err = excinfo.value
    assert err.status_code == 503
    assert err.busy
    assert err.retry_after == 3.0


def test_a_504_is_not_retried(mocker):
    timed_out = _response(mocker, 504, {"detail": "get_spectrum timed out"})
    get = mocker.patch("requests.Session.get", return_value=timed_out)
    sleep = mocker.patch.object(interface, "_sleep")

    sisi = SpectraInspectorServerInterface()
    with pytest.raises(ServerRequestError, match="timed out") as excinfo:
        sisi.image_data_summed("a-sample", (0, 10))
    assert get.call_count == 1
    assert not sleep.called
    assert excinfo.value.status_code == 504
    assert excinfo.value.busy


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, interface._DEFAULT_RETRY_AFTER_S),
        ("5", 5.0),
        ("0.5", 0.5),
        ("600", interface._MAX_RETRY_AFTER_S),
        ("soon", interface._DEFAULT_RETRY_AFTER_S),
        (format_datetime(interface.datetime(2000, 1, 1, tzinfo=interface.UTC)), 0.0),
    ],
)
def test_retry_after_header_as_seconds(mocker, raw, expected):
    headers = {} if raw is None else {"Retry-After": raw}
    response = _response(mocker, 503, {}, headers)
    assert interface._retry_after_seconds(response) == expected


@pytest.mark.parametrize(
    "call",
    [
        lambda sisi: sisi.get_available_datasets(),
        lambda sisi: sisi.get_image_metadata("nope"),
        lambda sisi: sisi.get_combined_image_metadata("nope"),
        lambda sisi: sisi.get_image_spectrum("nope"),
        lambda sisi: sisi.get_image("nope", 3),
        lambda sisi: sisi.image_data_summed("nope", (0, 3)),
    ],
    ids=[
        "available-datasets",
        "image-metadata",
        "image-metadata-combined",
        "image-spectrum",
        "image-data",
        "image-data-summed",
    ],
)
def test_every_data_call_raises_on_an_error_status(mocker, call):
    # rather than a pydantic error on the {"detail": ...} payload
    _mock_get(mocker, {"detail": "nope is not a valid sample"}, status_code=404)

    sisi = SpectraInspectorServerInterface()
    with pytest.raises(ServerRequestError, match="not a valid sample") as excinfo:
        call(sisi)
    assert excinfo.value.status_code == 404


@pytest.mark.parametrize(
    ("err", "fragment", "retryable"),
    [
        (ServerRequestError("busy", status_code=503), "busy", True),
        (ServerRequestError("timed out", status_code=504), "busy", True),
        (
            ServerRequestError("x is not a valid sample", status_code=404),
            "not found",
            False,
        ),
        (ServerRequestError("could not reach the backend"), "reach", True),
        (requests.exceptions.ConnectionError("refused"), "reach", True),
        (ServerRequestError("boom", status_code=500), "boom", False),
    ],
    ids=["503", "504", "404", "unreachable", "connection-error", "500"],
)
def test_load_failure_message_and_retry(err, fragment, retryable):
    failure = loadFailure.from_exception(err)
    assert fragment in failure.message.lower()
    assert failure.retryable is retryable

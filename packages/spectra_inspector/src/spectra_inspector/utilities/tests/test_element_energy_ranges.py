import pytest
import requests

from spectra_inspector.utilities import element_energy_ranges as eer

_SERVER_TABLE = {"Na": [0.96, 1.12], "Mg": [1.13, 1.34], "Fe": [6.275, 6.54]}


@pytest.fixture(autouse=True)
def _fresh_cache():
    eer.reset_cache()
    yield
    eer.reset_cache()


def _ok_response(mocker):
    response = mocker.Mock()
    response.status_code = 200
    response.json.return_value = {"ranges_keV": _SERVER_TABLE}
    return response


def test_ranges_come_from_the_server_in_server_order(mocker):
    mocker.patch("requests.Session.get", return_value=_ok_response(mocker))

    ranges = eer.get_element_energy_ranges()

    assert list(ranges) == ["Na", "Mg", "Fe"]
    assert ranges["Mg"] == (1.13, 1.34)
    assert all(isinstance(r, tuple) for r in ranges.values())


def test_ranges_are_fetched_once(mocker):
    get = mocker.patch("requests.Session.get", return_value=_ok_response(mocker))

    first = eer.get_element_energy_ranges()
    second = eer.get_element_energy_ranges()

    assert first == second
    assert get.call_count == 1


def test_callers_cannot_mutate_the_cache(mocker):
    mocker.patch("requests.Session.get", return_value=_ok_response(mocker))

    eer.get_element_energy_ranges().pop("Na")

    assert "Na" in eer.get_element_energy_ranges()


def test_unreachable_server_gives_no_presets_and_retries(mocker):
    get = mocker.patch(
        "requests.Session.get", side_effect=requests.exceptions.ConnectionError
    )

    assert eer.get_element_energy_ranges() == {}
    assert eer.get_element_energy_ranges() == {}
    assert get.call_count == 2

    get.side_effect = None
    get.return_value = _ok_response(mocker)
    assert list(eer.get_element_energy_ranges()) == ["Na", "Mg", "Fe"]


def test_server_error_gives_no_presets(mocker):
    response = mocker.Mock()
    response.status_code = 500
    response.json.return_value = {"detail": "boom"}
    mocker.patch("requests.Session.get", return_value=response)

    assert eer.get_element_energy_ranges() == {}

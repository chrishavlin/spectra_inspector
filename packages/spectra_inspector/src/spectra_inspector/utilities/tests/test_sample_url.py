import pytest

from spectra_inspector.utilities.sample_url import (
    sample_name_to_url,
    url_to_sample_name,
)


@pytest.mark.parametrize(
    "name",
    [
        "/TorresBoxSamples/test of server data/EN13/map20260930091127284_0.spd",
        "/Sample #3/area?1/map.spd",
        "/100% done/a+b/map.spd",
        "/already___underscored/map.spd",
        "/Übung 1/map.spd",
        "none",
    ],
)
def test_sample_name_round_trip(name):
    assert url_to_sample_name(sample_name_to_url(name)) == name


def test_sample_name_url_keeps_slashes_and_encodes_the_rest():
    url = sample_name_to_url("/dir with space/Sample #3/map.spd")
    assert url == "/dir%20with%20space/Sample%20%233/map.spd"
    assert "#" not in url
    assert "?" not in url

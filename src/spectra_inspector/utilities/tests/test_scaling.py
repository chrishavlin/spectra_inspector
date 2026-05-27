from spectra_inspector.server.model import EDAX_axis
from spectra_inspector.utilities.scaling import get_closest_index


def test_get_closest_index():

    ax = EDAX_axis(
        size=10,
        index_in_array=0,
        name="myaxis",
        scale=10,  # = dx
        offset=0,
        units="m",
        navigate=True,
    )

    assert get_closest_index(ax, 2) == 0
    assert get_closest_index(ax, -1) == 0
    assert get_closest_index(ax, 9) == 1
    assert get_closest_index(ax, 100) == 10


def test_get_closest_index_offset():

    ax = EDAX_axis(
        size=10,
        index_in_array=0,
        name="myaxis",
        scale=10,  # = dx
        offset=100,
        units="m",
        navigate=True,
    )

    assert get_closest_index(ax, 102) == 0
    assert get_closest_index(ax, 99) == 0
    assert get_closest_index(ax, 109) == 1
    assert get_closest_index(ax, 200) == 10

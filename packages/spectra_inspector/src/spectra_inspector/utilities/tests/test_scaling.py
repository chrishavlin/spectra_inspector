import pytest

from spectra_inspector.tests.test_export_summary import combined_metadata
from spectra_inspector.utilities.model import EDAX_axis
from spectra_inspector.utilities.scaling import get_closest_index, get_image_shape


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


@pytest.mark.parametrize("swap", [False, True])
def test_get_image_shape_reads_the_spatial_axes_by_name(swap):
    md = combined_metadata()
    md.axes_by_index["0"].size = 3
    md.axes_by_index["1"].size = 5
    if swap:
        # the names decide, not the array order
        md.axes_by_index["0"].name, md.axes_by_index["1"].name = "x", "y"
        assert get_image_shape(md) == (5, 3)
    else:
        assert get_image_shape(md) == (3, 5)


def test_get_image_shape_falls_back_to_array_order():
    md = combined_metadata()
    md.axes_by_index["0"].size = 3
    md.axes_by_index["1"].size = 5
    md.axes_by_index["0"].name = "rows"
    assert get_image_shape(md) == (3, 5)

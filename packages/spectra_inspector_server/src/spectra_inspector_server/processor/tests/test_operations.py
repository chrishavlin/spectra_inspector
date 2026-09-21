import numpy as np
import pytest

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import _on_disc_mock, createEDAXMock
from spectra_inspector_server.model import EDAX_raw_ds
from spectra_inspector_server.processor.operations import (
    OperationEDAXStateHandler,
)


def test_get_sample_axes_info(edax_path_handler: EDAXPathHandler) -> None:
    fake_filename = _on_disc_mock.filenames[0]
    ops = OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)
    axis_info = ops.get_sample_axes(fake_filename)
    assert len(axis_info) == 3


def test_get_single_channel_image(edax_path_handler: EDAXPathHandler) -> None:
    fake_filename = _on_disc_mock.filenames[0]
    ops = OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)
    axis_info = ops.get_sample_axes(fake_filename)

    im = ops.get_image(fake_filename, 2)

    shp = [0, 0, 0]
    for ax in axis_info:
        shp[ax.index_in_array] = ax.size
    expected_shp = tuple(shp[:-1])

    assert im.shape == expected_shp

    im = ops.get_image(fake_filename, 2, index0_range=(0, 4))
    new_expected = (4, expected_shp[1])
    assert im.shape == new_expected

    im = ops.get_image(fake_filename, 2, index1_range=(0, 5))
    new_expected = (expected_shp[1], 5)
    assert im.shape == new_expected

    im = ops.get_image(
        fake_filename,
        2,
        index0_range=(6, 8),
        index1_range=(2, 5),
    )
    assert im.shape == (2, 3)


def test_get_multi_channel_image(edax_path_handler: EDAXPathHandler) -> None:

    fake_filename = _on_disc_mock.filenames[0]
    ops = OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)
    axis_info = ops.get_sample_axes(fake_filename)

    im = ops.get_image(fake_filename, (0, 4))

    shp = [0, 0, 0]
    for ax in axis_info:
        shp[ax.index_in_array] = ax.size

    shp[-1] = 4
    expected_shp = tuple(shp)

    assert im.shape == expected_shp

    with pytest.raises(TypeError, match="unexpected type for channel_index"):
        _ = ops.get_image(fake_filename, [0, 4])  # type:ignore[arg-type]


def test_get_refined_metadata(edax_path_handler: EDAXPathHandler) -> None:
    fake_filename = _on_disc_mock.filenames[0]
    ops = OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)
    md = ops.get_refined_metadata(fake_filename)
    az = md.Acquisition_instrument.SEM.Detector.EDS.azimuth_angle
    assert np.isreal(az)


def test_get_spectrum(edax_path_handler: EDAXPathHandler) -> None:
    fake_filename = _on_disc_mock.filenames[0]
    ops = OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)
    s1d = ops.get_spectrum(fake_filename)
    assert s1d.energy_max > s1d.energy_min
    assert np.all(np.isreal(s1d.energy))
    assert np.all(np.isreal(s1d.intensity))

    s1d_2 = ops.get_spectrum(
        fake_filename,
        channel_range=(1, 5),
        index0_range=(0, 5),
        index1_range=(1, 3),
    )
    assert s1d.energy_max > s1d.energy_min
    assert np.all(np.isreal(s1d.energy))
    assert np.all(np.isreal(s1d.intensity))
    assert len(s1d_2.energy) == 4


@pytest.fixture
def fixed_mock(monkeypatch: pytest.MonkeyPatch) -> EDAX_raw_ds:
    """the on-disc mock rebuilds its random data on every load -- pin it down."""
    ds = createEDAXMock(im_shape=(16, 12, 10))
    monkeypatch.setattr(_on_disc_mock, "load", lambda _name, **_kwargs: ds)
    return ds


def test_spectrum_over_a_box_past_the_image_edge_sums_the_part_inside(
    edax_path_handler: EDAXPathHandler, fixed_mock: EDAX_raw_ds
) -> None:
    # a box dragged out past the map's edge reaches the server with indices
    # below zero or beyond the axis; it is summed over what lies inside
    cube = fixed_mock.data
    assert cube is not None
    fake_filename = _on_disc_mock.filenames[0]
    ops = OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)

    past_edge = ops.get_spectrum(
        fake_filename, index0_range=(-4, 5), index1_range=(3, 40)
    )
    np.testing.assert_array_equal(past_edge.intensity, cube[0:5, 3:12].sum(axis=(0, 1)))
    inside = ops.get_spectrum(fake_filename, index0_range=(0, 5), index1_range=(3, 12))
    assert past_edge.energy_min == inside.energy_min
    assert past_edge.energy_max == inside.energy_max

    outside = ops.get_spectrum(
        fake_filename, index0_range=(20, 24), index1_range=(0, 3)
    )
    assert len(outside.intensity) == cube.shape[2]
    assert not np.any(outside.intensity)


def test_image_over_a_box_past_the_image_edge_is_the_part_inside(
    edax_path_handler: EDAXPathHandler, fixed_mock: EDAX_raw_ds
) -> None:
    cube = fixed_mock.data
    assert cube is not None
    fake_filename = _on_disc_mock.filenames[0]
    ops = OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)

    im = ops.get_image(fake_filename, 2, index0_range=(-3, 4), index1_range=(10, 30))
    assert im.shape == (4, 2)
    np.testing.assert_array_equal(im, cube[0:4, 10:12, 2])

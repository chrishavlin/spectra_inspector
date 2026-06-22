import numpy as np
import pytest

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import _on_disc_mock


def test_axis_rescaling(edax_path_handler: EDAXPathHandler) -> None:
    fake_filename = _on_disc_mock.filenames[0]
    ds = edax_path_handler.load_edax(fake_filename)
    for axid in range(len(ds.axes)):
        minval, maxval = ds.axis_range(axid, indx_start=0, indx_end=None)
        assert minval == ds.axes_by_index[axid].offset
        fullsize = ds.axes_by_index[axid].scale * ds.axes_by_index[axid].size
        assert maxval == ds.axes_by_index[axid].offset + fullsize


def test_axis_rescaling_subset(edax_path_handler: EDAXPathHandler) -> None:
    fake_filename = _on_disc_mock.filenames[0]
    ds = edax_path_handler.load_edax(fake_filename)
    idx_0 = 2
    idx_1 = 8
    d_indx = idx_1 - idx_0
    for axid in range(len(ds.axes)):
        minval, maxval = ds.axis_range(axid, indx_start=idx_0, indx_end=idx_1)
        dist = maxval - minval
        assert np.allclose(
            [
                dist,
            ],
            [
                ds.axes_by_index[axid].scale * d_indx,
            ],
        )


def test_invalid_axis_args(edax_path_handler: EDAXPathHandler) -> None:
    fake_filename = _on_disc_mock.filenames[0]
    ds = edax_path_handler.load_edax(fake_filename)

    with pytest.raises(ValueError, match="start index cannot be < 0"):
        _ = ds.axis_range(1, indx_start=-1, indx_end=10)

    with pytest.raises(ValueError, match="end index is < start index"):
        _ = ds.axis_range(1, indx_start=5, indx_end=2)

    with pytest.raises(ValueError, match="end index cannot be > size of array"):
        _ = ds.axis_range(1, indx_start=5, indx_end=200)

import pytest

from spectra_inspector_server._testing import createEDAXMock
from spectra_inspector_server.model import EDAX_raw_ds


@pytest.mark.parametrize("im_shape", [None, (8, 16, 5)])
def test_createEDAXMock(im_shape: None | tuple[int, int, int]) -> None:
    ds = createEDAXMock(im_shape=im_shape)
    assert isinstance(ds, EDAX_raw_ds)

    for indx in range(3):
        ra_indx = ds.axes[indx].index_in_array
        sz = ds.axes[indx].size
        assert ds.data.shape[ra_indx] == sz

import numpy as np
import pytest

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import _on_disc_mock, createEDAXMock
from spectra_inspector_server.model import EDAX_raw_ds
from spectra_inspector_server.processor._reductions import (
    accumulator_dtype,
    chunk_bounds,
    fast_accumulator_limit,
)
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler


@pytest.mark.parametrize(
    ("dtype", "n_terms", "expected"),
    [
        (np.uint16, 4096, np.uint32),
        (np.uint16, 2**32, np.int64),
        (np.uint8, 4096, np.uint32),
        (np.int16, 4096, np.int32),
        (np.uint32, 2, np.int64),
        (np.int64, 1, np.int64),
    ],
)
def test_accumulator_dtype(dtype: type, n_terms: int, expected: type) -> None:
    assert accumulator_dtype(np.dtype(dtype), n_terms) == np.dtype(expected)


def test_accumulator_dtype_cannot_overflow() -> None:
    # the widest sum an accumulator has to hold is n_terms * the dtype max;
    # int64 is the widest on offer, so only check what it can express
    for dtype in (np.uint8, np.uint16, np.int16, np.uint32):
        for n_terms in (1, 17, 4096, 2**20):
            acc = accumulator_dtype(np.dtype(dtype), n_terms)
            assert n_terms * np.iinfo(dtype).max <= np.iinfo(acc).max


def test_fast_accumulator_limit() -> None:
    limit = fast_accumulator_limit(np.dtype(np.uint16))
    assert accumulator_dtype(np.dtype(np.uint16), limit).itemsize == 4
    assert accumulator_dtype(np.dtype(np.uint16), limit + 1).itemsize == 8
    # nothing can be summed into 32 bits when a single value may not fit
    assert fast_accumulator_limit(np.dtype(np.int64)) == 0


@pytest.mark.parametrize(
    ("start", "stop", "chunksize"),
    [(0, 400, 128), (3, 17, 5), (0, 5, 128), (7, 7, 4), (2, 9, 1)],
)
def test_chunk_bounds(start: int, stop: int, chunksize: int) -> None:
    chunks = chunk_bounds(start, stop, chunksize)
    assert [c[0] for c in chunks[1:]] == [c[1] for c in chunks[:-1]]
    if stop > start:
        assert chunks[0][0] == start
        assert chunks[-1][1] == stop
        assert max(c[1] - c[0] for c in chunks) <= chunksize
    else:
        assert chunks == []


@pytest.fixture(params=[np.int64, np.uint16])
def fixed_mock(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> EDAX_raw_ds:
    """the on-disc mock rebuilds its random data on every load -- pin it down."""
    ds = createEDAXMock(im_shape=(16, 16, 10))
    assert ds.data is not None
    ds.data = ds.data.astype(request.param)
    monkeypatch.setattr(_on_disc_mock, "load", lambda _name: ds)
    return ds


def _ops(edax_path_handler: EDAXPathHandler) -> OperationEDAXStateHandler:
    return OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)


@pytest.mark.parametrize("chunking_index", [0, 1, 2])
@pytest.mark.parametrize("chunksize", [1, 3, 128])
def test_summed_image_matches_direct_sum(
    edax_path_handler: EDAXPathHandler,
    fixed_mock: EDAX_raw_ds,
    chunking_index: int,
    chunksize: int,
) -> None:
    name = _on_disc_mock.filenames[0]
    ops = _ops(edax_path_handler)
    data = fixed_mock.data
    assert data is not None

    expected = data[2:9, 1:12, 3:8].sum(axis=-1)
    actual = ops.get_multi_channel_intensity_image(
        name,
        (3, 8),
        index0_range=(2, 9),
        index1_range=(1, 12),
        chunking_index=chunking_index,
        chunksize=chunksize,
    )
    assert np.array_equal(expected, actual)


@pytest.mark.parametrize("chunking_index", [0, 1])
@pytest.mark.parametrize("chunksize", [1, 3, 128])
def test_spectrum_matches_direct_sum(
    edax_path_handler: EDAXPathHandler,
    fixed_mock: EDAX_raw_ds,
    chunking_index: int,
    chunksize: int,
) -> None:
    name = _on_disc_mock.filenames[0]
    ops = _ops(edax_path_handler)
    data = fixed_mock.data
    assert data is not None

    expected = data[2:9, 1:12, 3:8].sum(axis=(0, 1))
    spectrum = ops.get_spectrum(
        name,
        channel_range=(3, 8),
        index0_range=(2, 9),
        index1_range=(1, 12),
        chunking_index=chunking_index,
        chunksize=chunksize,
    )
    assert np.array_equal(expected, spectrum.intensity)

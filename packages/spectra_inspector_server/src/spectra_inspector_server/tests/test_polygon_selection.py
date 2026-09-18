"""The polygon region: rasterising the vertices into a pixel mask and summing
the spectrum over it, through the operation and through the endpoint."""

import json
from collections.abc import Generator

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import _on_disc_mock, createEDAXMock
from spectra_inspector_server.main import app
from spectra_inspector_server.model import EDAX_raw_ds, Spectrum1dDict
from spectra_inspector_server.processor._polygon import polygon_bounds, polygon_mask
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler

TRIANGLE = [(1.0, 1.0), (1.0, 12.5), (13.0, 6.0)]
CONCAVE = [(0.5, 0.5), (0.5, 14.0), (14.0, 14.0), (14.0, 8.0), (6.0, 8.0), (6.0, 0.5)]


def _point_in_polygon(r: float, c: float, vertices: list[tuple[float, float]]) -> bool:
    """Reference even-odd test, one point at a time."""
    inside = False
    n = len(vertices)
    for i in range(n):
        ra, ca = vertices[i]
        rb, cb = vertices[(i + 1) % n]
        if (ra > r) != (rb > r):
            c_at = ca + (r - ra) * (cb - ca) / (rb - ra)
            if c < c_at:
                inside = not inside
    return inside


def _reference_mask(
    vertices: list[tuple[float, float]], shape: tuple[int, int]
) -> np.ndarray:
    full = np.zeros(shape, dtype=bool)
    for r in range(shape[0]):
        for c in range(shape[1]):
            full[r, c] = _point_in_polygon(r, c, vertices)
    return full


def _embed(
    mask: np.ndarray,
    index0_range: tuple[int, int],
    index1_range: tuple[int, int],
    shape: tuple[int, int],
) -> np.ndarray:
    full = np.zeros(shape, dtype=bool)
    full[index0_range[0] : index0_range[1], index1_range[0] : index1_range[1]] = mask
    return full


@pytest.mark.parametrize("vertices", [TRIANGLE, CONCAVE, list(reversed(CONCAVE))])
def test_mask_matches_point_by_point_test(vertices: list[tuple[float, float]]) -> None:
    shape = (16, 16)
    mask, index0_range, index1_range = polygon_mask(vertices, shape)
    assert mask.shape == (
        index0_range[1] - index0_range[0],
        index1_range[1] - index1_range[0],
    )
    assert mask.any()
    np.testing.assert_array_equal(
        _embed(mask, index0_range, index1_range, shape),
        _reference_mask(vertices, shape),
    )


def test_axis_aligned_polygon_is_the_half_open_box() -> None:
    # corners on pixel centres: the low edges are in, the high edges are out,
    # as they are for a box sliced [start, stop)
    square = [(2.0, 3.0), (2.0, 7.0), (6.0, 7.0), (6.0, 3.0)]
    mask, index0_range, index1_range = polygon_mask(square, (16, 16))
    assert (index0_range, index1_range) == ((2, 7), (3, 8))
    expected = np.zeros((5, 5), dtype=bool)
    expected[:4, :4] = True
    np.testing.assert_array_equal(mask, expected)


def test_bounds_are_clipped_to_the_image() -> None:
    vertices = [(-3.0, -3.0), (-3.0, 40.0), (40.0, 40.0), (40.0, -3.0)]
    assert polygon_bounds(vertices, (16, 12)) == ((0, 16), (0, 12))
    mask, _, _ = polygon_mask(vertices, (16, 12))
    assert mask.shape == (16, 12)
    assert mask.all()


def test_polygon_off_the_image_selects_nothing() -> None:
    vertices = [(20.0, 20.0), (20.0, 30.0), (30.0, 25.0)]
    mask, index0_range, index1_range = polygon_mask(vertices, (16, 16))
    assert mask.size == 0
    assert index0_range[0] == index0_range[1]
    assert index1_range[0] == index1_range[1]


@pytest.mark.parametrize(
    "vertices",
    [
        [(0.0, 0.0), (1.0, 1.0)],
        [(0.0, 0.0), (1.0, 1.0), (float("nan"), 2.0)],
    ],
)
def test_bad_polygons_are_rejected(vertices: list[tuple[float, float]]) -> None:
    with pytest.raises(ValueError, match="polygon"):
        polygon_mask(vertices, (16, 16))


@pytest.fixture
def app_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def fixed_mock(monkeypatch: pytest.MonkeyPatch) -> EDAX_raw_ds:
    """the on-disc mock rebuilds its random data on every load -- pin it down."""
    ds = createEDAXMock(im_shape=(16, 16, 10))
    monkeypatch.setattr(_on_disc_mock, "load", lambda _name, **_kwargs: ds)
    return ds


@pytest.fixture
def ops(edax_path_handler: EDAXPathHandler) -> OperationEDAXStateHandler:
    return OperationEDAXStateHandler(edax_path_handler, allow_mock_files=True)


def _cube(ds: EDAX_raw_ds) -> np.ndarray:
    assert ds.data is not None
    return ds.data


@pytest.mark.parametrize("chunking_index", [0, 1])
@pytest.mark.parametrize("chunksize", [1, 3, 128])
def test_spectrum_sums_the_pixels_inside_the_polygon(
    ops: OperationEDAXStateHandler,
    fixed_mock: EDAX_raw_ds,
    chunking_index: int,
    chunksize: int,
) -> None:
    cube = _cube(fixed_mock)
    shape = (cube.shape[0], cube.shape[1])
    mask, index0_range, index1_range = polygon_mask(CONCAVE, shape)
    expected = cube[_embed(mask, index0_range, index1_range, shape)].sum(axis=0)

    spectrum = ops.get_spectrum(
        _on_disc_mock.filenames[0],
        polygon=CONCAVE,
        chunking_index=chunking_index,
        chunksize=chunksize,
    )
    np.testing.assert_array_equal(spectrum.intensity, expected)
    assert len(spectrum.energy) == cube.shape[2]


def test_polygon_spectrum_with_a_channel_range(
    ops: OperationEDAXStateHandler, fixed_mock: EDAX_raw_ds
) -> None:
    cube = _cube(fixed_mock)
    shape = (cube.shape[0], cube.shape[1])
    mask, index0_range, index1_range = polygon_mask(TRIANGLE, shape)
    expected = cube[_embed(mask, index0_range, index1_range, shape)].sum(axis=0)

    spectrum = ops.get_spectrum(
        _on_disc_mock.filenames[0], polygon=TRIANGLE, channel_range=(2, 7)
    )
    np.testing.assert_array_equal(spectrum.intensity, expected[2:7])
    np.testing.assert_array_equal(spectrum.energy, np.arange(2, 7))


def test_polygon_overrides_the_index_ranges(
    ops: OperationEDAXStateHandler,
    fixed_mock: EDAX_raw_ds,  # noqa: ARG001
) -> None:
    sample = _on_disc_mock.filenames[0]
    with_box = ops.get_spectrum(
        sample, polygon=TRIANGLE, index0_range=(0, 2), index1_range=(0, 2)
    )
    without = ops.get_spectrum(sample, polygon=TRIANGLE)
    np.testing.assert_array_equal(with_box.intensity, without.intensity)


def test_empty_polygon_region_is_all_zeros(ops: OperationEDAXStateHandler) -> None:
    spectrum = ops.get_spectrum(
        _on_disc_mock.filenames[0], polygon=[(50.0, 50.0), (50.0, 60.0), (60.0, 55.0)]
    )
    assert not spectrum.intensity.any()


def test_image_spectrum_endpoint_with_polygon(app_client: TestClient) -> None:
    # the mock behind the endpoint is rebuilt with fresh random data per load
    # (in another process), so this checks the shape and a bound, not values
    response = app_client.get(
        "/image-spectrum",
        params={
            "sample_name": _on_disc_mock.filenames[0],
            "include_weights": False,
            "polygon": json.dumps(TRIANGLE),
        },
    )
    assert response.status_code == 200
    spectrum = Spectrum1dDict(**response.json())

    n_channels = _cube(createEDAXMock()).shape[2]
    assert len(spectrum.intensity) == n_channels
    assert len(spectrum.energy) == n_channels
    # the mock's values lie in [0, 10): the region holds fewer pixels than
    # the map, so the sum stays well under the whole map's worst case
    mask, _, _ = polygon_mask(TRIANGLE, (16, 16))
    assert all(0 <= v <= 10 * mask.sum() for v in spectrum.intensity)


@pytest.mark.parametrize(
    "polygon",
    [
        "not json",
        json.dumps([[0, 0], [1, 1]]),
        json.dumps([[0, 0], [1, 1], [2]]),
        json.dumps([[0, 0], [1, 1], ["2", 3]]),
        json.dumps([[0, 0], [1, 1], [True, 3]]),
        json.dumps({"points": [[0, 0], [1, 1], [2, 2]]}),
    ],
)
def test_image_spectrum_endpoint_rejects_bad_polygons(
    app_client: TestClient, polygon: str
) -> None:
    response = app_client.get(
        "/image-spectrum",
        params={"sample_name": _on_disc_mock.filenames[0], "polygon": polygon},
    )
    assert response.status_code == 422
    assert "polygon" in response.json()["detail"]

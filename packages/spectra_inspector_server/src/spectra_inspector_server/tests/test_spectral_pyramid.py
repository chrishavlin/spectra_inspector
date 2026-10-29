"""The spectral block pyramid (``processor/pyramid.py``): building it, reading
regions off it exactly, serving it from the derived data store through
``get_spectrum``, and the script that builds one per map
(``scripts/build_spectral_pyramids.py``).

As in ``test_derived_data.py``, the map under test is a stub fileset on a
``tmp_path`` data root whose ``.spd`` loaders are patched to hand back a
small synthetic cube.
"""

import importlib.util
import logging
import multiprocessing
import os
import shutil
import sys
from collections.abc import Generator
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
import zarr

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import (
    _on_disc_mock,
    createEDAXMock,
    write_mock_spc,
)
from spectra_inspector_server.model import EDAX_file_set
from spectra_inspector_server.processor import file_loaders, operations
from spectra_inspector_server.processor._polygon import polygon_mask
from spectra_inspector_server.processor._reductions import (
    chunk_bounds as real_chunk_bounds,
)
from spectra_inspector_server.processor.derived_data import (
    DerivedDataStore,
    clear_pyramid_cache,
)
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler
from spectra_inspector_server.processor.pyramid import (
    PyramidSpec,
    SpectralPyramid,
    block_sum,
    level_shape,
    pyramid_dtype,
    write_pyramid,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_spectral_pyramids.py"

# neither spatial extent divides the coarsest block, so every level has
# partial blocks along its bottom and right edges
CUBE_SHAPE = (37, 29, 60)
SAMPLE = "C-1"
SPEC = PyramidSpec(block_sizes=(2, 4, 8))

TRIANGLE = [(2.0, 3.0), (2.0, 25.0), (35.0, 20.0)]
CONCAVE = [
    (0.5, 0.5),
    (0.5, 27.0),
    (36.0, 27.0),
    (36.0, 14.0),
    (12.0, 14.0),
    (12.0, 0.5),
]
OFF_THE_EDGE = [(-5.0, -5.0), (-5.0, 50.0), (50.0, 50.0), (50.0, -5.0)]


@pytest.fixture
def cube() -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.random(CUBE_SHAPE) * 1000).astype(np.uint16)


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    directory = root / "session-a" / "nested"
    directory.mkdir(parents=True)
    (directory / f"{SAMPLE}.spd").write_bytes(b"stands in for the cube")
    (directory / f"{SAMPLE}.ipr").write_bytes(b"stands in for the ipr")
    write_mock_spc(directory / f"{SAMPLE}.spc")
    return root


@pytest.fixture(autouse=True)
def patched_spd_loaders(
    monkeypatch: pytest.MonkeyPatch, cube: np.ndarray
) -> Generator[None]:
    mock = createEDAXMock(im_shape=CUBE_SHAPE)

    def fake_metadata(_edax_files: EDAX_file_set) -> dict[str, Any]:
        return {
            "axes": [ax.model_dump() for ax in mock.axes],
            "metadata": mock.metadata,
            "original_metadata": mock.original_metadata,
        }

    monkeypatch.setattr(file_loaders, "load_edax_spd_metadata", fake_metadata)
    monkeypatch.setattr(
        file_loaders, "load_spd_into_memmap", lambda _header, _path: cube
    )
    file_loaders.clear_edax_cache()
    clear_pyramid_cache()
    yield
    file_loaders.clear_edax_cache()
    clear_pyramid_cache()


@pytest.fixture
def cube_reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Every chunked pass over the cube by the handler's own reduction; the
    pyramid path never makes one."""
    reads: list[tuple[int, int]] = []

    def counting(start: int, stop: int, chunksize: int) -> list[tuple[int, int]]:
        reads.append((start, stop))
        return real_chunk_bounds(start, stop, chunksize)

    monkeypatch.setattr(operations, "chunk_bounds", counting)
    return reads


@pytest.fixture
def ph(data_root: Path) -> EDAXPathHandler:
    return EDAXPathHandler(data_root, init_db=True)


@pytest.fixture
def store(tmp_path: Path, data_root: Path) -> DerivedDataStore:
    return DerivedDataStore(tmp_path / "derived", data_root)


@pytest.fixture
def ops(ph: EDAXPathHandler, store: DerivedDataStore) -> OperationEDAXStateHandler:
    return OperationEDAXStateHandler(ph, allow_mock_files=True, derived_data=store)


@pytest.fixture
def pyramid(tmp_path: Path, cube: np.ndarray) -> SpectralPyramid:
    path = tmp_path / "pyramid.zarr"
    write_pyramid(path, cube, SPEC, {"stamp": [1, 2]}, name="test")
    return SpectralPyramid.open(path)


def _fileset(ph: EDAXPathHandler) -> EDAX_file_set:
    return ph.database.available_maps[SAMPLE]


def _bump_mtime(path: Path, seconds: int = 1) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + seconds * 10**9))


def _reference(
    cube: np.ndarray,
    mask: np.ndarray | None,
    index0_range: tuple[int, int],
    index1_range: tuple[int, int],
    channel_range: tuple[int, int] = (0, CUBE_SHAPE[2]),
) -> np.ndarray:
    box = cube[
        index0_range[0] : index0_range[1],
        index1_range[0] : index1_range[1],
        channel_range[0] : channel_range[1],
    ]
    if mask is None:
        return np.asarray(box.sum(axis=(0, 1), dtype=np.int64))
    return np.asarray(box[mask].sum(axis=0, dtype=np.int64))


# ---------------------------------------------------------------------------
# the spec


@pytest.mark.parametrize(
    "block_sizes", [(), (1,), (1, 2), (4, 6), (4, 4), (8, 4), (4, 16, 24)]
)
def test_spec_rejects_a_bad_layout(block_sizes: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match=r"block size|level"):
        PyramidSpec(block_sizes=block_sizes)
    with pytest.raises(ValueError, match="chunk_blocks"):
        PyramidSpec(chunk_blocks=0)


def test_spec_levels_and_factors() -> None:
    spec = PyramidSpec(block_sizes=(4, 16, 64))
    assert spec.n_levels == 3
    assert spec.refinement_factors == (4, 4)
    assert PyramidSpec.from_factors(4, (4, 4)) == spec
    assert PyramidSpec.from_factors(8, ()).block_sizes == (8,)
    assert PyramidSpec(block_sizes=(2, 6, 12)).refinement_factors == (3, 2)


# ---------------------------------------------------------------------------
# building


@pytest.mark.parametrize("block_size", [1, 2, 3, 8, 37, 40])
def test_block_sum_matches_a_loop(cube: np.ndarray, block_size: int) -> None:
    out = block_sum(cube, block_size, np.dtype(np.int64))
    assert out.shape == level_shape(CUBE_SHAPE, block_size)
    for i in range(out.shape[0]):
        for j in range(out.shape[1]):
            block = cube[
                i * block_size : (i + 1) * block_size,
                j * block_size : (j + 1) * block_size,
            ]
            np.testing.assert_array_equal(out[i, j], block.sum(axis=(0, 1)))


def test_levels_are_block_sums_of_the_cube(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    assert pyramid.block_sizes == SPEC.block_sizes
    assert pyramid.source_shape == CUBE_SHAPE
    assert pyramid.key == {"stamp": [1, 2]}
    for level, b in enumerate(SPEC.block_sizes):
        array = pyramid.levels[level]
        assert array.dtype == pyramid_dtype(cube.dtype, SPEC) == np.uint32
        assert array.shape == level_shape(CUBE_SHAPE, b)
        np.testing.assert_array_equal(array[:], block_sum(cube, b, np.dtype(np.uint32)))


def test_the_group_is_ome_ngff_multiscales(tmp_path: Path, cube: np.ndarray) -> None:
    path = tmp_path / "pyramid.zarr"
    write_pyramid(path, cube, SPEC, {"stamp": [1, 2]}, name="C-1")
    group = zarr.open_group(path, mode="r")
    assert group.metadata.zarr_format == 3
    attrs: dict[str, Any] = dict(group.attrs)
    ome = attrs["ome"]
    assert ome["version"] == "0.5"
    (multiscale,) = ome["multiscales"]
    assert multiscale["name"] == "C-1"
    assert multiscale["type"] == "sum"
    assert [ax["name"] for ax in multiscale["axes"]] == ["index0", "index1", "channel"]
    assert [ax["type"] for ax in multiscale["axes"]] == ["space", "space", "channel"]
    assert [d["path"] for d in multiscale["datasets"]] == ["0", "1", "2"]
    for dataset, b in zip(multiscale["datasets"], SPEC.block_sizes, strict=True):
        scale, translation = dataset["coordinateTransformations"]
        assert scale == {"type": "scale", "scale": [b, b, 1.0]}
        assert translation["translation"] == [(b - 1) / 2, (b - 1) / 2, 0.0]
        array = group[dataset["path"]]
        assert isinstance(array, zarr.Array)
        assert array.chunks[2] == CUBE_SHAPE[2]
    info = attrs["spectra_inspector"]
    assert info["kind"] == "spectral_block_pyramid"
    assert info["source_shape"] == list(CUBE_SHAPE)
    assert info["block_sizes"] == list(SPEC.block_sizes)


def test_a_pyramid_from_a_wider_dtype_or_huge_blocks(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    cube = (rng.random((9, 7, 5)) * 10).astype(np.int64)
    spec = PyramidSpec(block_sizes=(2, 4))
    write_pyramid(tmp_path / "wide.zarr", cube, spec, {})
    wide = SpectralPyramid.open(tmp_path / "wide.zarr")
    assert wide.levels[0].dtype == np.int64
    spectrum, _ = wide.region_spectrum(cube, None, (1, 8), (0, 7), (0, 5))
    np.testing.assert_array_equal(spectrum, cube[1:8].sum(axis=(0, 1)))

    # 512 x 512 of uint16 can overflow 32 bits, so the levels widen
    spec = PyramidSpec(block_sizes=(512,))
    assert pyramid_dtype(np.dtype(np.uint16), spec) == np.int64
    assert pyramid_dtype(np.dtype(np.uint16), PyramidSpec((256,))) == np.uint32


def test_write_replaces_an_existing_group(tmp_path: Path, cube: np.ndarray) -> None:
    path = tmp_path / "pyramid.zarr"
    write_pyramid(path, cube, SPEC, {"stamp": [1, 2]})
    write_pyramid(path, cube, PyramidSpec(block_sizes=(4,)), {"stamp": [3, 4]})
    pyramid = SpectralPyramid.open(path)
    assert pyramid.block_sizes == (4,)
    assert pyramid.key == {"stamp": [3, 4]}
    assert not (path / "1").exists()


def test_open_rejects_something_else(tmp_path: Path) -> None:
    group = zarr.open_group(tmp_path / "other.zarr", mode="w")
    with pytest.raises(ValueError, match="not a spectral block pyramid"):
        SpectralPyramid(group)
    with pytest.raises(FileNotFoundError):
        SpectralPyramid.open(tmp_path / "missing.zarr")


# ---------------------------------------------------------------------------
# reading regions


@pytest.mark.parametrize(
    ("index0_range", "index1_range"),
    [
        ((0, 37), (0, 29)),  # the whole map: coarse blocks only
        ((3, 30), (5, 20)),  # every level and a raw ring
        ((0, 8), (0, 8)),  # exactly one coarsest block
        ((8, 16), (8, 12)),  # one middle block
        ((1, 2), (1, 2)),  # one pixel
        ((30, 37), (20, 29)),  # the bottom-right corner, partial blocks only
        ((0, 37), (0, 1)),  # a line thinner than any block
        ((16, 24), (0, 29)),  # a full-width strip
        ((4, 4), (0, 29)),  # empty
    ],
)
def test_box_spectrum_is_exact(
    pyramid: SpectralPyramid,
    cube: np.ndarray,
    index0_range: tuple[int, int],
    index1_range: tuple[int, int],
) -> None:
    spectrum, stats = pyramid.region_spectrum(
        cube, None, index0_range, index1_range, (0, CUBE_SHAPE[2])
    )
    assert spectrum.dtype == np.int64
    np.testing.assert_array_equal(
        spectrum, _reference(cube, None, index0_range, index1_range)
    )
    area = (index0_range[1] - index0_range[0]) * (index1_range[1] - index1_range[0])
    assert stats.selected_pixels == area
    assert stats.raw_pixels <= area
    covered = sum(
        n * b * b for n, b in zip(stats.blocks_per_level, SPEC.block_sizes, strict=True)
    )
    # edge blocks hold fewer pixels, so block pixels can only overshoot
    assert covered + stats.raw_pixels >= area


def test_read_stats_describe_the_request(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    mask, index0_range, index1_range = polygon_mask(CONCAVE, CUBE_SHAPE[:2])
    _, stats = pyramid.region_spectrum(cube, mask, index0_range, index1_range, (0, 30))
    assert stats.block_sizes == SPEC.block_sizes
    assert all(
        chunks <= blocks
        for chunks, blocks in zip(
            stats.chunks_per_level, stats.blocks_per_level, strict=True
        )
    )
    assert all(chunks > 0 for chunks in stats.chunks_per_level)
    # a chunk holds 16 x 16 blocks (or the whole level) over the 30 channels asked for
    for level, b in enumerate(SPEC.block_sizes):
        chunk_rows, chunk_cols = (min(16, n) for n in level_shape(CUBE_SHAPE, b)[:2])
        assert stats.chunk_bytes_per_level[level] == chunk_rows * chunk_cols * 30 * 4
    assert stats.chunk_bytes == sum(
        n * size
        for n, size in zip(
            stats.chunks_per_level, stats.chunk_bytes_per_level, strict=True
        )
    )
    assert stats.block_pixels + stats.raw_pixels >= stats.selected_pixels
    assert stats.block_seconds > 0
    assert stats.raw_seconds > 0
    summary = stats.summary()
    assert summary.startswith(
        f"{stats.selected_pixels} pixels selected; level 2 (8px): "
    )
    assert f"{stats.raw_pixels} raw boundary pixels (" in summary
    assert "MB of chunks decoded" in summary


def test_get_spectrum_logs_what_the_pyramid_cost(
    ops: OperationEDAXStateHandler,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube: np.ndarray,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="spectra_inspector")
    ops.get_spectrum(SAMPLE, polygon=TRIANGLE)
    (off_the_cube,) = [r for r in caplog.records if "summed off the cube" in r.message]
    assert off_the_cube.message.startswith(
        f"{SAMPLE}: polygon in [2:36, 3:26], channels [0:60]"
    )

    assert store.store_pyramid(_fileset(ph), cube, SPEC)
    ops.get_spectrum(SAMPLE, index0_range=(3, 30), index1_range=(5, 20))
    (served,) = [r for r in caplog.records if "from the pyramid" in r.message]
    assert served.levelno == logging.DEBUG
    assert served.message.startswith(
        f"{SAMPLE}: box [3:30, 5:20], channels [0:60] from the pyramid: 405 pixels selected; "
    )
    assert "raw boundary pixels" in served.message

    ops.get_spectrum(SAMPLE, index0_range=(3, 30), use_pyramid=False)
    assert "(pyramid disabled)" in caplog.records[-1].message


def test_the_whole_map_needs_no_raw_pixels(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    _, stats = pyramid.region_spectrum(cube, None, (0, 37), (0, 29), (0, 60))
    assert stats.raw_pixels == 0
    assert stats.blocks_per_level == (0, 0, 5 * 4)


def test_a_block_aligned_box_needs_no_raw_pixels(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    _, stats = pyramid.region_spectrum(cube, None, (8, 24), (8, 24), (0, 60))
    assert stats.blocks_per_level == (0, 0, 4)
    assert stats.raw_pixels == 0
    assert stats.selected_pixels == 256


def test_a_thin_line_is_all_raw(pyramid: SpectralPyramid, cube: np.ndarray) -> None:
    _, stats = pyramid.region_spectrum(cube, None, (0, 37), (3, 4), (0, 60))
    assert stats.blocks_per_level == (0, 0, 0)
    assert stats.raw_pixels == 37


@pytest.mark.parametrize("vertices", [TRIANGLE, CONCAVE, OFF_THE_EDGE])
@pytest.mark.parametrize("channel_range", [(0, 60), (5, 40), (59, 60)])
def test_polygon_spectrum_is_exact(
    pyramid: SpectralPyramid,
    cube: np.ndarray,
    vertices: list[tuple[float, float]],
    channel_range: tuple[int, int],
) -> None:
    mask, index0_range, index1_range = polygon_mask(vertices, CUBE_SHAPE[:2])
    spectrum, stats = pyramid.region_spectrum(
        cube, mask, index0_range, index1_range, channel_range
    )
    np.testing.assert_array_equal(
        spectrum, _reference(cube, mask, index0_range, index1_range, channel_range)
    )
    assert stats.selected_pixels == int(mask.sum())
    assert stats.raw_pixels < stats.selected_pixels
    assert sum(stats.blocks_per_level) > 0


def test_raw_reads_scale_with_the_boundary(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    mask, index0_range, index1_range = polygon_mask(CONCAVE, CUBE_SHAPE[:2])
    _, stats = pyramid.region_spectrum(cube, mask, index0_range, index1_range, (0, 60))
    # the ring the finest blocks cannot fill is at most 2 pixels wide
    assert stats.raw_pixels < stats.selected_pixels / 5


def test_only_the_boundary_pixels_are_read_from_the_cube(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    mask, index0_range, index1_range = polygon_mask(TRIANGLE, CUBE_SHAPE[:2])
    seen: list[np.ndarray] = []

    class Recording(np.ndarray):
        def __getitem__(self, item: Any) -> Any:
            if isinstance(item, tuple) and isinstance(item[0], np.ndarray):
                seen.append(np.stack([item[0], item[1]], axis=1))
            return np.ndarray.__getitem__(self, item)

    recording = cube.view(Recording)
    _, stats = pyramid.region_spectrum(
        recording, mask, index0_range, index1_range, (0, 60)
    )
    pixels = np.concatenate(seen)
    assert len(pixels) == stats.raw_pixels
    full_mask = np.zeros(CUBE_SHAPE[:2], dtype=bool)
    full_mask[index0_range[0] : index0_range[1], index1_range[0] : index1_range[1]] = (
        mask
    )
    assert full_mask[pixels[:, 0], pixels[:, 1]].all()


def test_region_rejects_a_mismatched_cube_or_mask(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    with pytest.raises(ValueError, match="pyramid was built from"):
        pyramid.region_spectrum(cube[:-1], None, (0, 5), (0, 5), (0, 60))
    with pytest.raises(ValueError, match="mask shape"):
        pyramid.region_spectrum(
            cube, np.ones((3, 3), dtype=bool), (0, 5), (0, 5), (0, 60)
        )


def test_an_empty_selection_or_channel_range(
    pyramid: SpectralPyramid, cube: np.ndarray
) -> None:
    mask = np.zeros((10, 10), dtype=bool)
    spectrum, stats = pyramid.region_spectrum(cube, mask, (0, 10), (0, 10), (0, 60))
    assert spectrum.shape == (60,)
    assert not spectrum.any()
    assert stats.blocks_per_level == (0, 0, 0)
    assert (stats.raw_pixels, stats.selected_pixels) == (0, 0)
    spectrum, _ = pyramid.region_spectrum(cube, None, (0, 10), (0, 10), (7, 7))
    assert spectrum.shape == (0,)


# ---------------------------------------------------------------------------
# through the store and the handler


def test_store_builds_and_serves_a_pyramid(
    ph: EDAXPathHandler, store: DerivedDataStore, cube: np.ndarray
) -> None:
    fileset = _fileset(ph)
    assert not store.has_pyramid(fileset)
    assert store.load_pyramid(fileset) is None
    assert store.store_pyramid(fileset, cube, SPEC)
    assert store.pyramid_path(fileset) == (
        store.derived_dir / "session-a" / "nested" / SAMPLE / "pyramid.zarr"
    )
    assert not list(store.pyramid_path(fileset).parent.glob("*.tmp"))

    pyramid = store.load_pyramid(fileset)
    assert pyramid is not None
    assert pyramid.key == store.pyramid_key(fileset, SPEC)
    assert pyramid.key["fileset"] == f"session-a/nested/{SAMPLE}.spd"
    assert pyramid.key["op"] == "pyramid"
    assert pyramid.key["args"] == {"block_sizes": [2, 4, 8]}
    assert store.has_pyramid(fileset)
    assert store.has_pyramid(fileset, SPEC)
    assert not store.has_pyramid(fileset, PyramidSpec(block_sizes=(4,)))

    # the same object is handed back while it stays valid
    assert store.load_pyramid(fileset) is pyramid


def test_a_stale_pyramid_is_a_miss(
    ph: EDAXPathHandler, store: DerivedDataStore, cube: np.ndarray
) -> None:
    fileset = _fileset(ph)
    assert store.store_pyramid(fileset, cube, SPEC)
    assert store.has_pyramid(fileset)
    _bump_mtime(fileset.spd)
    assert not store.has_pyramid(fileset)
    assert store.store_pyramid(fileset, cube, SPEC)
    assert store.has_pyramid(fileset)


def test_a_broken_pyramid_is_a_miss(
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube: np.ndarray,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fileset = _fileset(ph)
    path = store.pyramid_path(fileset)
    path.mkdir(parents=True)
    (path / "zarr.json").write_text("{not json")
    assert store.load_pyramid(fileset) is None
    assert "could not open the pyramid" in caplog.text

    shutil.rmtree(path)
    zarr.open_group(path, mode="w")
    assert store.load_pyramid(fileset) is None

    # a group with the right key but a level missing
    assert store.store_pyramid(fileset, cube, SPEC)
    clear_pyramid_cache()
    shutil.rmtree(path / "2")
    assert store.load_pyramid(fileset) is None


def test_store_pyramid_replaces_an_existing_one(
    ph: EDAXPathHandler, store: DerivedDataStore, cube: np.ndarray
) -> None:
    fileset = _fileset(ph)
    assert store.store_pyramid(fileset, cube, SPEC)
    assert store.store_pyramid(fileset, cube, PyramidSpec(block_sizes=(4,)))
    pyramid = store.load_pyramid(fileset)
    assert pyramid is not None
    assert pyramid.block_sizes == (4,)
    entry_dir = store.pyramid_path(fileset).parent
    assert sorted(p.name for p in entry_dir.iterdir()) == ["pyramid.zarr"]


def test_store_pyramid_honours_write_on_miss(
    ph: EDAXPathHandler, data_root: Path, tmp_path: Path, cube: np.ndarray
) -> None:
    reader = DerivedDataStore(tmp_path / "derived", data_root, write_on_miss=False)
    assert not reader.store_pyramid(_fileset(ph), cube, SPEC)
    assert not reader.derived_dir.exists()


def test_a_fileset_outside_the_data_root_is_never_stored(
    tmp_path: Path, ph: EDAXPathHandler, cube: np.ndarray
) -> None:
    elsewhere = DerivedDataStore(tmp_path / "derived", tmp_path / "another_root")
    assert not elsewhere.store_pyramid(_fileset(ph), cube, SPEC)
    assert elsewhere.load_pyramid(_fileset(ph)) is None
    assert not elsewhere.derived_dir.exists()


@pytest.mark.parametrize(
    ("index0_range", "index1_range", "polygon"),
    [
        ((3, 30), (5, 20), None),
        (None, None, TRIANGLE),
        (None, None, CONCAVE),
    ],
)
def test_get_spectrum_answers_from_the_pyramid(
    ops: OperationEDAXStateHandler,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
    index0_range: tuple[int, int] | None,
    index1_range: tuple[int, int] | None,
    polygon: list[tuple[float, float]] | None,
) -> None:
    def request(**kwargs: Any) -> Any:
        return ops.get_spectrum(
            SAMPLE,
            index0_range=index0_range,
            index1_range=index1_range,
            polygon=polygon,
            **kwargs,
        )

    before = request()
    assert len(cube_reads) == 1

    assert store.store_pyramid(_fileset(ph), cube, SPEC)
    after = request(channel_range=(5, 40))
    assert len(cube_reads) == 1
    np.testing.assert_array_equal(after.intensity, before.intensity[5:40])
    np.testing.assert_array_equal(after.energy, before.energy[5:40])
    assert after.metadata == before.metadata
    assert after.original_metadata == before.original_metadata

    forced = request(channel_range=(5, 40), use_pyramid=False)
    assert len(cube_reads) == 2
    np.testing.assert_array_equal(forced.intensity, after.intensity)


def test_get_spectrum_falls_back_when_the_pyramid_is_stale(
    ops: OperationEDAXStateHandler,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
) -> None:
    assert store.store_pyramid(_fileset(ph), cube, SPEC)
    ops.get_spectrum(SAMPLE, polygon=TRIANGLE)
    assert len(cube_reads) == 0
    _bump_mtime(_fileset(ph).spd)
    ops.get_spectrum(SAMPLE, polygon=TRIANGLE)
    assert len(cube_reads) == 1


def test_a_full_extent_spectrum_from_the_pyramid_is_stored(
    ops: OperationEDAXStateHandler,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
) -> None:
    assert store.store_pyramid(_fileset(ph), cube, SPEC)
    spectrum = ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 0
    np.testing.assert_array_equal(spectrum.intensity, cube.sum(axis=(0, 1)))
    assert store.has_entry(_fileset(ph), "spectrum", {"channel_range": None})


def test_mock_samples_and_spc_spectra_never_use_a_pyramid(
    ops: OperationEDAXStateHandler, cube_reads: list[tuple[int, int]]
) -> None:
    ops.get_spectrum(_on_disc_mock.filenames[0], index0_range=(0, 4))
    assert len(cube_reads) == 1
    spc = ops.get_spectrum(SAMPLE, spectrum_only=True)
    assert spc.intensity.ndim == 1
    assert len(cube_reads) == 1


def test_no_store_means_no_pyramid(
    ph: EDAXPathHandler, cube_reads: list[tuple[int, int]]
) -> None:
    ops = OperationEDAXStateHandler(ph)
    ops.get_spectrum(SAMPLE, polygon=TRIANGLE)
    assert len(cube_reads) == 1


# ---------------------------------------------------------------------------
# the build script


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_spectral_pyramids", BUILD_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def build_script() -> ModuleType:
    if not BUILD_SCRIPT.is_file():
        pytest.skip(f"{BUILD_SCRIPT} is not part of this checkout")
    return _load_script()


def _add_map(data_root: Path, name: str) -> None:
    directory = data_root / "session-b"
    directory.mkdir(exist_ok=True)
    for suffix in (".spd", ".ipr"):
        shutil.copy(
            data_root / "session-a" / "nested" / f"{SAMPLE}{suffix}",
            directory / f"{name}{suffix}",
        )
    write_mock_spc(directory / f"{name}.spc")


def test_script_builds_every_map_under_the_root(
    build_script: ModuleType,
    data_root: Path,
    store: DerivedDataStore,
    ops: OperationEDAXStateHandler,
    cube_reads: list[tuple[int, int]],
) -> None:
    _add_map(data_root, "D-2")
    report = build_script.build_pyramids(data_root, store.derived_dir, spec=SPEC)
    assert (report.up_to_date, report.built, report.skipped_filesets) == (0, 2, 0)
    assert (
        store.derived_dir / "session-a" / "nested" / SAMPLE / "pyramid.zarr"
    ).is_dir()
    assert (store.derived_dir / "session-b" / "D-2" / "pyramid.zarr").is_dir()
    assert not list(store.derived_dir.rglob("*.tmp"))

    # re-running is cheap
    report = build_script.build_pyramids(data_root, store.derived_dir, spec=SPEC)
    assert (report.up_to_date, report.built, report.skipped_filesets) == (2, 0, 0)

    # and the handler serves what it built
    ops.get_spectrum(SAMPLE, polygon=TRIANGLE)
    assert len(cube_reads) == 0


def test_script_rebuilds_a_stale_or_different_pyramid(
    build_script: ModuleType,
    data_root: Path,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
) -> None:
    build_script.build_pyramids(data_root, store.derived_dir, spec=SPEC)
    other = PyramidSpec(block_sizes=(4, 8))
    report = build_script.build_pyramids(data_root, store.derived_dir, spec=other)
    assert (report.up_to_date, report.built) == (0, 1)
    pyramid = store.load_pyramid(_fileset(ph))
    assert pyramid is not None
    assert pyramid.block_sizes == (4, 8)

    _bump_mtime(_fileset(ph).spd)
    report = build_script.build_pyramids(data_root, store.derived_dir, spec=other)
    assert (report.up_to_date, report.built) == (0, 1)
    report = build_script.build_pyramids(
        data_root, store.derived_dir, spec=other, overwrite=True
    )
    assert (report.up_to_date, report.built) == (0, 1)


def test_script_restricts_to_samples(
    build_script: ModuleType, data_root: Path, store: DerivedDataStore
) -> None:
    _add_map(data_root, "D-2")
    report = build_script.build_pyramids(
        data_root, store.derived_dir, spec=SPEC, samples=("D-2",)
    )
    assert (report.up_to_date, report.built) == (0, 1)
    assert not (store.derived_dir / "session-a").exists()
    with pytest.raises(ValueError, match="no such maps"):
        build_script.build_pyramids(
            data_root, store.derived_dir, spec=SPEC, samples=("nope",)
        )


def test_script_skips_a_fileset_it_cannot_read(
    build_script: ModuleType,
    data_root: Path,
    store: DerivedDataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(_edax_files: EDAX_file_set) -> dict[str, Any]:
        msg = "unreadable header"
        raise OSError(msg)

    monkeypatch.setattr(file_loaders, "load_edax_spd_metadata", broken)
    report = build_script.build_pyramids(data_root, store.derived_dir, spec=SPEC)
    assert (report.up_to_date, report.built, report.skipped_filesets) == (0, 0, 1)
    assert not list(store.derived_dir.rglob("*.tmp"))


def test_script_honours_mixed_basenames(
    build_script: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "mixed_root"
    directory = root / "sample"
    directory.mkdir(parents=True)
    for name in ("map123_0.spd", "map123_0.spc", "map123_0.xml", "fov_1.ipr"):
        (directory / name).write_bytes(b"stub")
    derived_dir = tmp_path / "mixed_derived"

    report = build_script.build_pyramids(root, derived_dir, spec=SPEC)
    assert report.built == 0
    report = build_script.build_pyramids(
        root, derived_dir, spec=SPEC, allow_mixed_basenames=True
    )
    assert report.built == 1
    assert (derived_dir / "sample" / "map123_0" / "pyramid.zarr").is_dir()


@pytest.mark.skipif(
    sys.platform == "win32", reason="the patched loaders only reach forked workers"
)
def test_script_spreads_maps_over_workers(
    build_script: ModuleType, data_root: Path, store: DerivedDataStore
) -> None:
    _add_map(data_root, "D-2")
    fork = multiprocessing.get_context("fork")
    report = build_script.build_pyramids(
        data_root, store.derived_dir, spec=SPEC, workers=2, mp_context=fork
    )
    assert (report.up_to_date, report.built, report.skipped_filesets) == (0, 2, 0)
    report = build_script.build_pyramids(
        data_root, store.derived_dir, spec=SPEC, workers=2, mp_context=fork
    )
    assert (report.up_to_date, report.built) == (2, 0)
    with pytest.raises(ValueError, match="workers must be at least 1"):
        build_script.build_pyramids(data_root, store.derived_dir, workers=0)


def test_script_main(
    build_script: ModuleType,
    data_root: Path,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = [str(data_root), str(store.derived_dir), "--block-sizes", "2", "8"]
    assert build_script.main(argv) == 0
    assert "0 pyramids already up to date, 1 built" in capsys.readouterr().out
    pyramid = store.load_pyramid(_fileset(ph))
    assert pyramid is not None
    assert pyramid.block_sizes == (2, 8)

    assert build_script.main(argv) == 0
    assert "1 pyramids already up to date, 0 built" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        build_script.main([*argv[:2], "--block-sizes", "4", "6"])
    assert "--block-sizes" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        build_script.main([*argv, "--workers", "0"])
    assert "--workers must be at least 1" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        build_script.main([*argv, "--samples", "nope"])
    assert "no such maps" in capsys.readouterr().err


def test_script_main_falls_back_to_the_settings(
    build_script: ModuleType,
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cwd = tmp_path / "server_package"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    with pytest.raises(SystemExit):
        build_script.main([str(data_root)])
    assert "DERIVED_DATA_DIR is unset" in capsys.readouterr().err

    derived_dir = tmp_path / "env_derived"
    (cwd / ".env").write_text(
        f"SPECTRA_INSPECTOR_DATA_ROOT='{data_root}'\n"
        f"SPECTRA_INSPECTOR_DERIVED_DATA_DIR='{derived_dir}'\n"
    )
    assert build_script.main(["--block-sizes", "2", "4"]) == 0
    assert "1 built" in capsys.readouterr().out
    assert any(derived_dir.rglob("pyramid.zarr"))

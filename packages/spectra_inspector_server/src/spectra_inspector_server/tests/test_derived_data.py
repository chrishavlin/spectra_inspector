"""The on-disk derived data store (``processor/derived_data.py``) and the
script that fills it (``scripts/precompute_derived_data.py``).

The map under test is a stub fileset on a ``tmp_path`` data root with a
genuine ``.spc``, whose ``.spd`` loaders are patched to hand back a small
synthetic cube, so the store is exercised through the real key (relative
path plus file stamp) without any EDAX data.
"""

import ast
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

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import (
    _on_disc_mock,
    createEDAXMock,
    write_mock_spc,
)
from spectra_inspector_server.calibration import element_energy_ranges_keV
from spectra_inspector_server.dependencies import get_derived_data_store, get_settings
from spectra_inspector_server.model import EDAX_axis, EDAX_file_set
from spectra_inspector_server.processor import file_loaders, operations
from spectra_inspector_server.processor._reductions import (
    chunk_bounds as real_chunk_bounds,
)
from spectra_inspector_server.processor.derived_data import (
    DEFAULT_PRECOMPUTE_ELEMENTS,
    OP_IMAGE,
    OP_SPECTRUM,
    DerivedDataStore,
    channel_range_for_window,
)
from spectra_inspector_server.processor.operations import (
    IndexRangeError,
    OperationEDAXStateHandler,
)
from spectra_inspector_server.settings import ENV_PREFIX, Settings

REPO_ROOT = Path(__file__).resolve().parents[5]
PRECOMPUTE_SCRIPT = REPO_ROOT / "scripts" / "precompute_derived_data.py"
FRONTEND_SCALING = (
    REPO_ROOT
    / "packages"
    / "spectra_inspector"
    / "src"
    / "spectra_inspector"
    / "utilities"
    / "scaling.py"
)

# 400 channels of 5 eV span 2 keV: the Na, Mg, Al and Si windows fit, Fe does not
CUBE_SHAPE = (6, 5, 400)
SAMPLE = "C-1"
CHANNEL_RANGE = (10, 30)


@pytest.fixture
def cube() -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.random(CUBE_SHAPE) * 100).astype(np.uint16)


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
    yield
    file_loaders.clear_edax_cache()


@pytest.fixture
def cube_reads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Every chunked pass over the cube: both reductions go through
    ``chunk_bounds`` before they touch the data, so a hit makes none."""
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


def _fileset(ph: EDAXPathHandler) -> EDAX_file_set:
    return ph.database.available_maps[SAMPLE]


def _bump_mtime(path: Path, seconds: int = 1) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + seconds * 10**9))


# ---------------------------------------------------------------------------
# the handler


def test_entries_mirror_the_data_tree(
    ops: OperationEDAXStateHandler, store: DerivedDataStore, cube: np.ndarray
) -> None:
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_spectrum(SAMPLE)

    entry_dir = store.derived_dir / "session-a" / "nested" / SAMPLE
    assert (entry_dir / "image_10-30.npz").is_file()
    assert (entry_dir / "spectrum.npz").is_file()
    assert not list(entry_dir.glob("*.tmp"))

    with np.load(entry_dir / "image_10-30.npz") as entry:
        np.testing.assert_array_equal(
            entry["array"], cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
        )


def test_second_call_does_not_touch_the_cube(
    ops: OperationEDAXStateHandler,
    cube_reads: list[tuple[int, int]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="spectra_inspector")
    image = ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    spectrum = ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 2
    assert not [r for r in caplog.records if "served" in r.message]

    again = ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    spectrum_again = ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 2
    served = [r for r in caplog.records if "served" in r.message]
    assert [r.levelno for r in served] == [logging.DEBUG, logging.DEBUG]
    assert "served image from" in served[0].message
    assert "served spectrum from" in served[1].message

    np.testing.assert_array_equal(again, image)
    assert again.dtype == np.int64
    np.testing.assert_array_equal(spectrum_again.intensity, spectrum.intensity)
    np.testing.assert_array_equal(spectrum_again.energy, spectrum.energy)
    assert spectrum_again.energy_min == spectrum.energy_min
    assert spectrum_again.energy_max == spectrum.energy_max
    assert spectrum_again.metadata == spectrum.metadata
    assert spectrum_again.original_metadata == spectrum.original_metadata


def test_different_arguments_are_different_entries(
    ops: OperationEDAXStateHandler, cube_reads: list[tuple[int, int]]
) -> None:
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_multi_channel_intensity_image(SAMPLE, (10, 31))
    ops.get_spectrum(SAMPLE)
    ops.get_spectrum(SAMPLE, channel_range=(0, 100))
    assert len(cube_reads) == 4

    ops.get_multi_channel_intensity_image(SAMPLE, (10, 31))
    ops.get_spectrum(SAMPLE, channel_range=(0, 100))
    assert len(cube_reads) == 4


def test_a_changed_stamp_misses(
    ops: OperationEDAXStateHandler,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube_reads: list[tuple[int, int]],
) -> None:
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == 1

    args = {"channel_range": list(CHANNEL_RANGE)}
    assert store.has_entry(_fileset(ph), OP_IMAGE, args)
    _bump_mtime(_fileset(ph).spd)
    assert not store.has_entry(_fileset(ph), OP_IMAGE, args)

    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == 2
    # the recomputation replaced the stale entry
    assert store.has_entry(_fileset(ph), OP_IMAGE, args)
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == 2


@pytest.mark.parametrize(
    ("index0_range", "index1_range"),
    [((0, 3), None), (None, (1, 5)), ((0, 6), (0, 4))],
)
def test_sub_extent_requests_bypass_the_store(
    ops: OperationEDAXStateHandler,
    store: DerivedDataStore,
    cube_reads: list[tuple[int, int]],
    index0_range: tuple[int, int] | None,
    index1_range: tuple[int, int] | None,
) -> None:
    def sub_extent() -> None:
        ops.get_multi_channel_intensity_image(
            SAMPLE, CHANNEL_RANGE, index0_range=index0_range, index1_range=index1_range
        )
        ops.get_spectrum(SAMPLE, index0_range=index0_range, index1_range=index1_range)

    sub_extent()
    assert not store.derived_dir.exists()

    # a full-extent entry does not serve a sub-extent request either
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 4
    sub_extent()
    assert len(cube_reads) == 6
    assert len(list(store.derived_dir.rglob("*.npz"))) == 2


def test_polygon_requests_bypass_the_store(
    ops: OperationEDAXStateHandler,
    store: DerivedDataStore,
    cube_reads: list[tuple[int, int]],
) -> None:
    # a polygon covering the whole map still sums the full extent, and is
    # still not a storable request
    polygon = [(-1.0, -1.0), (-1.0, 10.0), (10.0, 10.0), (10.0, -1.0)]
    ops.get_spectrum(SAMPLE)
    ops.get_spectrum(SAMPLE, polygon=polygon)
    ops.get_spectrum(SAMPLE, polygon=polygon)
    assert len(cube_reads) == 3
    assert len(list(store.derived_dir.rglob("*.npz"))) == 1


def test_explicit_full_extent_ranges_hit(
    ops: OperationEDAXStateHandler, cube_reads: list[tuple[int, int]]
) -> None:
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_multi_channel_intensity_image(
        SAMPLE,
        CHANNEL_RANGE,
        index0_range=(0, CUBE_SHAPE[0]),
        index1_range=(0, CUBE_SHAPE[1]),
    )
    assert len(cube_reads) == 1


def test_a_partially_written_entry_is_ignored(
    ops: OperationEDAXStateHandler,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
) -> None:
    args = {"channel_range": list(CHANNEL_RANGE)}
    path = store.entry_path(_fileset(ph), OP_IMAGE, args)
    path.parent.mkdir(parents=True)

    # a write that never finished leaves a temp name, which is never read
    (path.with_name(path.name + ".123.deadbeef.tmp")).write_bytes(b"PK\x03\x04half")
    expected = cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
    np.testing.assert_array_equal(
        ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
    )
    assert len(cube_reads) == 1

    # a truncated entry under the final name is a miss, logged, and replaced
    whole = path.read_bytes()
    path.write_bytes(whole[: len(whole) // 2])
    assert not store.has_entry(_fileset(ph), OP_IMAGE, args)
    np.testing.assert_array_equal(
        ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
    )
    assert len(cube_reads) == 2
    assert store.has_entry(_fileset(ph), OP_IMAGE, args)

    # so is something that is not an npz at all, or an npz of the wrong shape
    path.write_bytes(b"not an archive")
    assert store.lookup(_fileset(ph), OP_IMAGE, args, expected.shape) is None
    store.store(_fileset(ph), OP_IMAGE, args, expected[:2])
    assert store.lookup(_fileset(ph), OP_IMAGE, args, expected.shape) is None
    np.testing.assert_array_equal(
        ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
    )
    assert len(cube_reads) == 3


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="a mode bit does not stop writes for root, or at all on Windows",
)
def test_an_unwritable_derived_dir_only_disables_writing(
    ops: OperationEDAXStateHandler,
    store: DerivedDataStore,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
) -> None:
    store.derived_dir.mkdir()
    store.derived_dir.chmod(0o500)
    try:
        expected = cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
        for _ in range(2):
            np.testing.assert_array_equal(
                ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
            )
        assert len(cube_reads) == 2
        assert not list(store.derived_dir.iterdir())
    finally:
        store.derived_dir.chmod(0o700)


def test_a_fileset_outside_the_data_root_is_never_stored(
    tmp_path: Path, ph: EDAXPathHandler, cube: np.ndarray
) -> None:
    elsewhere = DerivedDataStore(tmp_path / "derived", tmp_path / "another_root")
    ops = OperationEDAXStateHandler(ph, derived_data=elsewhere)
    expected = cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
    np.testing.assert_array_equal(
        ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
    )
    assert not elsewhere.derived_dir.exists()


def test_mock_samples_are_not_stored(
    ops: OperationEDAXStateHandler, store: DerivedDataStore
) -> None:
    ops.get_multi_channel_intensity_image(_on_disc_mock.filenames[0], (0, 4))
    ops.get_spectrum(_on_disc_mock.filenames[0])
    assert not store.derived_dir.exists()


def test_no_store_without_the_setting(
    ph: EDAXPathHandler, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops = OperationEDAXStateHandler(ph)
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert not list(tmp_path.rglob("*.npz"))

    # both are lru_cached, and an earlier test may have filled them from a
    # developer's .env that does set the directory
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    get_derived_data_store.cache_clear()
    try:
        assert Settings().derived_data_dir is None
        assert get_derived_data_store() is None
    finally:
        get_settings.cache_clear()
        get_derived_data_store.cache_clear()


def test_the_settings_are_read_from_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(f"{ENV_PREFIX}DERIVED_DATA_DIR='/srv/store'\n")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.derived_data_dir == "/srv/store"
    assert s.derived_write_on_miss is False

    get_settings.cache_clear()
    get_derived_data_store.cache_clear()
    try:
        store = get_derived_data_store()
        assert store is not None
        assert store.write_on_miss is False
    finally:
        get_settings.cache_clear()
        get_derived_data_store.cache_clear()

    (tmp_path / ".env").write_text(
        f"{ENV_PREFIX}DERIVED_DATA_DIR='/srv/store'\n{ENV_PREFIX}DERIVED_WRITE_ON_MISS=true\n"
    )
    assert Settings().derived_write_on_miss is True


def test_write_on_miss_off_makes_the_store_read_only(
    ph: EDAXPathHandler,
    data_root: Path,
    tmp_path: Path,
    cube_reads: list[tuple[int, int]],
) -> None:
    writer = DerivedDataStore(tmp_path / "derived", data_root)
    reader = DerivedDataStore(tmp_path / "derived", data_root, write_on_miss=False)
    ops = OperationEDAXStateHandler(ph, derived_data=reader)

    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_spectrum(SAMPLE)
    assert not reader.derived_dir.exists()

    # what the precompute script wrote is still served
    OperationEDAXStateHandler(ph, derived_data=writer).get_spectrum(SAMPLE)
    assert len(cube_reads) == 3
    ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 3


# ---------------------------------------------------------------------------
# the single-pass reduction


@pytest.mark.parametrize("chunking_index", [0, 1])
@pytest.mark.parametrize("chunksize", [128, 4, 1])
def test_one_pass_matches_the_separate_reductions(
    ph: EDAXPathHandler,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
    chunksize: int,
    chunking_index: int,
) -> None:
    ops = OperationEDAXStateHandler(ph)
    windows = [CHANNEL_RANGE, (0, 400), (399, 400), (50, 50)]

    spectrum, images = ops.get_spectrum_and_images(
        SAMPLE, windows, chunksize=chunksize, chunking_index=chunking_index
    )
    assert len(cube_reads) == 1
    assert spectrum is not None
    np.testing.assert_array_equal(
        spectrum.intensity, cube.sum(axis=(0, 1), dtype=np.int64)
    )
    assert len(images) == len(windows)
    for image, (start, stop) in zip(images, windows, strict=True):
        assert image.dtype == np.int64
        np.testing.assert_array_equal(
            image, cube[:, :, start:stop].sum(axis=-1, dtype=np.int64)
        )

    separate = ops.get_spectrum(SAMPLE)
    np.testing.assert_array_equal(spectrum.energy, separate.energy)
    assert (spectrum.energy_min, spectrum.energy_max) == (
        separate.energy_min,
        separate.energy_max,
    )
    assert spectrum.metadata == separate.metadata
    assert spectrum.original_metadata == separate.original_metadata


def test_one_pass_without_the_spectrum(
    ph: EDAXPathHandler, cube: np.ndarray, cube_reads: list[tuple[int, int]]
) -> None:
    ops = OperationEDAXStateHandler(ph)
    spectrum, images = ops.get_spectrum_and_images(
        SAMPLE, [CHANNEL_RANGE], include_spectrum=False
    )
    assert spectrum is None
    assert len(cube_reads) == 1
    np.testing.assert_array_equal(
        images[0], cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
    )

    assert ops.get_spectrum_and_images(SAMPLE, [], include_spectrum=False) == (
        None,
        [],
    )


@pytest.mark.parametrize("window", [(0, 401), (-1, 10), (30, 10)])
def test_one_pass_rejects_a_window_past_the_axis(
    ph: EDAXPathHandler, window: tuple[int, int]
) -> None:
    ops = OperationEDAXStateHandler(ph)
    with pytest.raises(IndexRangeError, match="index2 range"):
        ops.get_spectrum_and_images(SAMPLE, [window])


def test_one_pass_fills_every_entry(
    ops: OperationEDAXStateHandler,
    store: DerivedDataStore,
    cube_reads: list[tuple[int, int]],
) -> None:
    windows = [CHANNEL_RANGE, (100, 150)]
    spectrum, images = ops.get_spectrum_and_images(SAMPLE, windows)
    assert len(cube_reads) == 1
    assert len(list(store.derived_dir.rglob("*.npz"))) == 3

    assert spectrum is not None
    np.testing.assert_array_equal(
        ops.get_spectrum(SAMPLE).intensity, spectrum.intensity
    )
    for image, window in zip(images, windows, strict=True):
        np.testing.assert_array_equal(
            ops.get_multi_channel_intensity_image(SAMPLE, window), image
        )
    assert len(cube_reads) == 1


def test_one_pass_on_a_mock_sample_writes_nothing(
    ops: OperationEDAXStateHandler, store: DerivedDataStore
) -> None:
    spectrum, images = ops.get_spectrum_and_images(_on_disc_mock.filenames[0], [(0, 4)])
    assert spectrum is not None
    assert images[0].shape == (16, 16)
    assert not store.derived_dir.exists()


# ---------------------------------------------------------------------------
# the precompute script


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "precompute_derived_data", PRECOMPUTE_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve the script's deferred annotations through sys.modules
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def precompute_script() -> ModuleType:
    if not PRECOMPUTE_SCRIPT.is_file():
        pytest.skip(f"{PRECOMPUTE_SCRIPT} is not part of this checkout")
    return _load_script()


def test_script_writes_entries_the_handler_hits(
    precompute_script: ModuleType,
    data_root: Path,
    store: DerivedDataStore,
    ops: OperationEDAXStateHandler,
    cube_reads: list[tuple[int, int]],
) -> None:
    n_entries = 1 + len(DEFAULT_PRECOMPUTE_ELEMENTS)

    report = precompute_script.precompute(data_root, store.derived_dir)
    assert (report.hits, report.writes, report.skipped_filesets) == (0, n_entries, 0)
    # every entry of a map comes from one pass over its cube
    assert len(cube_reads) == 1
    assert len(list(store.derived_dir.rglob("*.npz"))) == n_entries

    # re-running is cheap: every entry is up to date
    report = precompute_script.precompute(data_root, store.derived_dir)
    assert (report.hits, report.writes, report.skipped_filesets) == (n_entries, 0, 0)
    assert len(cube_reads) == 1

    # the default view's requests are all hits
    channel_axis = ops.get_sample_axes(SAMPLE)[2]
    ops.get_spectrum(SAMPLE)
    for element in DEFAULT_PRECOMPUTE_ELEMENTS:
        window = element_energy_ranges_keV[element]
        ops.get_multi_channel_intensity_image(
            SAMPLE, channel_range_for_window(channel_axis, window)
        )
    assert len(cube_reads) == 1

    # a window the script did not image is still a miss
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == 2


def test_script_computes_only_what_is_missing(
    precompute_script: ModuleType,
    data_root: Path,
    store: DerivedDataStore,
    ops: OperationEDAXStateHandler,
    cube_reads: list[tuple[int, int]],
) -> None:
    ops.get_spectrum(SAMPLE)
    channel_axis = ops.get_sample_axes(SAMPLE)[2]
    ops.get_multi_channel_intensity_image(
        SAMPLE, channel_range_for_window(channel_axis, element_energy_ranges_keV["Si"])
    )
    assert len(cube_reads) == 2

    report = precompute_script.precompute(data_root, store.derived_dir)
    assert (report.hits, report.writes) == (2, 2)
    assert len(cube_reads) == 3

    # two elements sharing a window are one image
    report = precompute_script.precompute(
        data_root, store.derived_dir, elements=("Na", "Na", "Mg")
    )
    assert (report.hits, report.writes) == (2, 1)
    assert len(cube_reads) == 4


def test_script_skips_a_fileset_whose_axis_is_too_short_for_a_window(
    precompute_script: ModuleType, data_root: Path, store: DerivedDataStore
) -> None:
    report = precompute_script.precompute(
        data_root, store.derived_dir, elements=("Fe",)
    )
    assert (report.hits, report.writes, report.skipped_filesets) == (0, 0, 1)


def test_script_elements_and_stamps(
    precompute_script: ModuleType,
    data_root: Path,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
) -> None:
    report = precompute_script.precompute(
        data_root, store.derived_dir, elements=("Na",)
    )
    assert (report.hits, report.writes) == (0, 2)

    _bump_mtime(_fileset(ph).spd)
    report = precompute_script.precompute(
        data_root, store.derived_dir, elements=("Na",)
    )
    assert (report.hits, report.writes) == (0, 2)

    with pytest.raises(ValueError, match="no energy window for \\['Xx'\\]"):
        precompute_script.precompute(data_root, store.derived_dir, elements=("Xx",))


def test_script_skips_a_fileset_it_cannot_read(
    precompute_script: ModuleType,
    data_root: Path,
    store: DerivedDataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(_edax_files: EDAX_file_set) -> dict[str, Any]:
        msg = "unreadable header"
        raise OSError(msg)

    monkeypatch.setattr(file_loaders, "load_edax_spd_metadata", broken)
    report = precompute_script.precompute(data_root, store.derived_dir)
    assert (report.hits, report.writes, report.skipped_filesets) == (0, 0, 1)


def test_script_honours_mixed_basenames(
    precompute_script: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "mixed_root"
    directory = root / "sample"
    directory.mkdir(parents=True)
    for name in ("map123_0.spd", "map123_0.spc", "map123_0.xml", "fov_1.ipr"):
        (directory / name).write_bytes(b"stub")
    derived_dir = tmp_path / "mixed_cache"

    report = precompute_script.precompute(root, derived_dir)
    assert report.writes == 0
    report = precompute_script.precompute(root, derived_dir, allow_mixed_basenames=True)
    assert report.writes == 1 + len(DEFAULT_PRECOMPUTE_ELEMENTS)
    assert (derived_dir / "sample" / "map123_0" / "spectrum.npz").is_file()


@pytest.mark.skipif(
    sys.platform == "win32", reason="the patched loaders only reach forked workers"
)
def test_script_spreads_filesets_over_workers(
    precompute_script: ModuleType,
    data_root: Path,
    store: DerivedDataStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # a second map, so there is one fileset per worker
    other = data_root / "session-b"
    other.mkdir()
    for name in (f"{SAMPLE}.spd", f"{SAMPLE}.ipr"):
        shutil.copy(data_root / "session-a" / "nested" / name, other / f"D-2{name[3:]}")
    write_mock_spc(other / "D-2.spc")
    fork = multiprocessing.get_context("fork")

    report = precompute_script.precompute(
        data_root, store.derived_dir, workers=2, mp_context=fork
    )
    assert (report.hits, report.writes, report.skipped_filesets) == (0, 8, 0)
    assert (store.derived_dir / "session-b" / "D-2" / "spectrum.npz").is_file()

    report = precompute_script.precompute(
        data_root, store.derived_dir, workers=2, mp_context=fork
    )
    assert (report.hits, report.writes) == (8, 0)

    with pytest.raises(ValueError, match="workers must be at least 1"):
        precompute_script.precompute(data_root, store.derived_dir, workers=0)
    with pytest.raises(SystemExit):
        precompute_script.main(
            [str(data_root), str(store.derived_dir), "--workers", "0"]
        )
    assert "--workers must be at least 1" in capsys.readouterr().err


def test_script_overwrite_empties_the_directory_first(
    precompute_script: ModuleType,
    data_root: Path,
    ph: EDAXPathHandler,
    store: DerivedDataStore,
    cube_reads: list[tuple[int, int]],
) -> None:
    report = precompute_script.precompute(data_root, store.derived_dir)
    assert report.writes == 1 + len(DEFAULT_PRECOMPUTE_ELEMENTS)
    stray = store.derived_dir / "unrelated.txt"
    stray.write_text("not an entry")
    stale = store.entry_path(_fileset(ph), OP_IMAGE, {"channel_range": [1, 2]})
    stale.write_bytes(b"from an older run")

    reads_before = len(cube_reads)
    report = precompute_script.precompute(data_root, store.derived_dir, overwrite=True)
    assert (report.hits, report.writes) == (0, 1 + len(DEFAULT_PRECOMPUTE_ELEMENTS))
    assert len(cube_reads) == reads_before + 1
    assert not stray.exists()
    assert not stale.exists()
    assert store.derived_dir.is_dir()
    assert store.has_entry(_fileset(ph), OP_SPECTRUM, {"channel_range": None})

    # a missing directory is nothing to empty
    missing = store.derived_dir.parent / "never_made"
    precompute_script.empty_derived_dir(missing, data_root)
    assert not missing.exists()


@pytest.mark.parametrize(
    "derived",
    [
        Path("data_root"),
        Path("data_root") / "session-a",
        Path(),
    ],
    ids=["is the data root", "inside it", "contains it"],
)
def test_script_refuses_to_empty_the_data_root(
    precompute_script: ModuleType, data_root: Path, tmp_path: Path, derived: Path
) -> None:
    before = sorted(data_root.rglob("*"))
    with pytest.raises(ValueError, match="refusing to empty"):
        precompute_script.precompute(data_root, tmp_path / derived, overwrite=True)
    assert sorted(data_root.rglob("*")) == before


def test_script_main(
    precompute_script: ModuleType,
    data_root: Path,
    store: DerivedDataStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        precompute_script.main(
            [str(data_root), str(store.derived_dir), "--elements", "Mg", "Si"]
        )
        == 0
    )
    assert "3 written" in capsys.readouterr().out
    assert (
        precompute_script.main(
            [str(data_root), str(store.derived_dir), "--elements", "Mg", "--overwrite"]
        )
        == 0
    )
    assert "0 entries already up to date, 2 written" in capsys.readouterr().out
    shutil.rmtree(store.derived_dir)


def test_script_main_falls_back_to_the_settings(
    precompute_script: ModuleType,
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cwd = tmp_path / "server_package"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    for key in ("DATA_ROOT", "DERIVED_DATA_DIR", "DB_ALLOW_MIXED_BASENAMES"):
        monkeypatch.delenv(ENV_PREFIX + key, raising=False)

    with pytest.raises(SystemExit):
        precompute_script.main([str(data_root)])
    assert "DERIVED_DATA_DIR is unset" in capsys.readouterr().err

    derived_dir = tmp_path / "env_cache"
    (cwd / ".env").write_text(
        f"{ENV_PREFIX}DATA_ROOT='{data_root}'\n"
        f"{ENV_PREFIX}DERIVED_DATA_DIR='{derived_dir}'\n"
    )
    assert precompute_script.main(["--elements", "Mg"]) == 0
    assert "2 written" in capsys.readouterr().out
    assert any(derived_dir.rglob("spectrum.npz"))

    # a mixed-basename root is only scanned as one when the .env says so
    mixed_root = tmp_path / "mixed_root"
    (mixed_root / "sample").mkdir(parents=True)
    for name in ("map123_0.spd", "map123_0.spc", "map123_0.xml", "fov_1.ipr"):
        (mixed_root / "sample" / name).write_bytes(b"stub")
    mixed_cache = tmp_path / "mixed_cache"
    assert precompute_script.main([str(mixed_root), str(mixed_cache)]) == 0
    assert "0 written" in capsys.readouterr().out
    (cwd / ".env").write_text(
        f"{ENV_PREFIX}DERIVED_DATA_DIR='{mixed_cache}'\n"
        f"{ENV_PREFIX}DB_ALLOW_MIXED_BASENAMES=true\n"
    )
    assert precompute_script.main([str(mixed_root), "--elements", "Mg"]) == 0
    assert "2 written" in capsys.readouterr().out
    assert (mixed_cache / "sample" / "map123_0" / "spectrum.npz").is_file()


# ---------------------------------------------------------------------------
# the window -> channel rule is the frontend's


def _frontend_get_closest_index() -> Any:
    """The frontend's ``get_closest_index``, lifted out of its module source:
    the frontend package is not importable from here."""
    tree = ast.parse(FRONTEND_SCALING.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "get_closest_index"
    )
    namespace: dict[str, Any] = {"np": np, "EDAX_axis": EDAX_axis}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), "<frontend>", "exec"),
        namespace,
    )
    return namespace["get_closest_index"]


@pytest.mark.skipif(
    not FRONTEND_SCALING.is_file(), reason="the frontend package is not checked out"
)
@pytest.mark.parametrize(
    ("scale", "offset"), [(0.005, 0.0), (0.01, 0.0), (0.01, -0.1), (0.0025, 0.02)]
)
def test_channel_range_matches_the_frontend(scale: float, offset: float) -> None:
    frontend = _frontend_get_closest_index()
    axis = EDAX_axis(
        size=4096,
        index_in_array=2,
        name="Energy",
        scale=scale,
        offset=offset,
        units="keV",
        navigate=False,
    )
    for window in element_energy_ranges_keV.values():
        expected = (frontend(axis, window[0]), frontend(axis, window[1]))
        assert channel_range_for_window(axis, window) == expected

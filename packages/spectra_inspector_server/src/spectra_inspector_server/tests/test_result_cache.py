"""The on-disk result cache (``processor/result_cache.py``) and the script
that fills it (``scripts/precompute_result_cache.py``).

The map under test is a stub fileset on a ``tmp_path`` data root with a
genuine ``.spc``, whose ``.spd`` loaders are patched to hand back a small
synthetic cube, so the cache is exercised through the real key (relative
path plus file stamp) without any EDAX data.
"""

import ast
import importlib.util
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
from spectra_inspector_server.dependencies import get_result_cache, get_settings
from spectra_inspector_server.model import EDAX_axis, EDAX_file_set
from spectra_inspector_server.processor import file_loaders, operations
from spectra_inspector_server.processor._reductions import (
    chunk_bounds as real_chunk_bounds,
)
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler
from spectra_inspector_server.processor.result_cache import (
    DEFAULT_PRECOMPUTE_ELEMENTS,
    OP_IMAGE,
    ResultCache,
    channel_range_for_window,
)
from spectra_inspector_server.settings import ENV_PREFIX, Settings

REPO_ROOT = Path(__file__).resolve().parents[5]
PRECOMPUTE_SCRIPT = REPO_ROOT / "scripts" / "precompute_result_cache.py"
FRONTEND_SCALING = (
    REPO_ROOT
    / "packages"
    / "spectra_inspector"
    / "src"
    / "spectra_inspector"
    / "utilities"
    / "scaling.py"
)

# 400 channels of 5 eV span 2 keV, past the Si window the script images
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
    ``chunk_bounds`` before they touch the data, so a cache hit makes none."""
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
def cache(tmp_path: Path, data_root: Path) -> ResultCache:
    return ResultCache(tmp_path / "cache", data_root)


@pytest.fixture
def ops(ph: EDAXPathHandler, cache: ResultCache) -> OperationEDAXStateHandler:
    return OperationEDAXStateHandler(ph, allow_mock_files=True, result_cache=cache)


def _fileset(ph: EDAXPathHandler) -> EDAX_file_set:
    return ph.database.available_maps[SAMPLE]


def _bump_mtime(path: Path, seconds: int = 1) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + seconds * 10**9))


# ---------------------------------------------------------------------------
# the handler


def test_entries_mirror_the_data_tree(
    ops: OperationEDAXStateHandler, cache: ResultCache, cube: np.ndarray
) -> None:
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_spectrum(SAMPLE)

    entry_dir = cache.cache_dir / "session-a" / "nested" / SAMPLE
    assert (entry_dir / "image_10-30.npz").is_file()
    assert (entry_dir / "spectrum.npz").is_file()
    assert not list(entry_dir.glob("*.tmp"))

    with np.load(entry_dir / "image_10-30.npz") as entry:
        np.testing.assert_array_equal(
            entry["array"], cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
        )


def test_second_call_does_not_touch_the_cube(
    ops: OperationEDAXStateHandler, cube_reads: list[tuple[int, int]]
) -> None:
    image = ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    spectrum = ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 2

    again = ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    spectrum_again = ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 2

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
    cache: ResultCache,
    cube_reads: list[tuple[int, int]],
) -> None:
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == 1

    args = {"channel_range": list(CHANNEL_RANGE)}
    assert cache.has_entry(_fileset(ph), OP_IMAGE, args)
    _bump_mtime(_fileset(ph).spd)
    assert not cache.has_entry(_fileset(ph), OP_IMAGE, args)

    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == 2
    # the recomputation replaced the stale entry
    assert cache.has_entry(_fileset(ph), OP_IMAGE, args)
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == 2


@pytest.mark.parametrize(
    ("index0_range", "index1_range"),
    [((0, 3), None), (None, (1, 5)), ((0, 6), (0, 4))],
)
def test_sub_extent_requests_bypass_the_cache(
    ops: OperationEDAXStateHandler,
    cache: ResultCache,
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
    assert not cache.cache_dir.exists()

    # a full-extent entry does not serve a sub-extent request either
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 4
    sub_extent()
    assert len(cube_reads) == 6
    assert len(list(cache.cache_dir.rglob("*.npz"))) == 2


def test_polygon_requests_bypass_the_cache(
    ops: OperationEDAXStateHandler,
    cache: ResultCache,
    cube_reads: list[tuple[int, int]],
) -> None:
    # a polygon covering the whole map still sums the full extent, and is
    # still not a cacheable request
    polygon = [(-1.0, -1.0), (-1.0, 10.0), (10.0, 10.0), (10.0, -1.0)]
    ops.get_spectrum(SAMPLE)
    ops.get_spectrum(SAMPLE, polygon=polygon)
    ops.get_spectrum(SAMPLE, polygon=polygon)
    assert len(cube_reads) == 3
    assert len(list(cache.cache_dir.rglob("*.npz"))) == 1


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
    cache: ResultCache,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
) -> None:
    args = {"channel_range": list(CHANNEL_RANGE)}
    path = cache.entry_path(_fileset(ph), OP_IMAGE, args)
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
    assert not cache.has_entry(_fileset(ph), OP_IMAGE, args)
    np.testing.assert_array_equal(
        ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
    )
    assert len(cube_reads) == 2
    assert cache.has_entry(_fileset(ph), OP_IMAGE, args)

    # so is something that is not an npz at all, or an npz of the wrong shape
    path.write_bytes(b"not an archive")
    assert cache.lookup(_fileset(ph), OP_IMAGE, args, expected.shape) is None
    cache.store(_fileset(ph), OP_IMAGE, args, expected[:2])
    assert cache.lookup(_fileset(ph), OP_IMAGE, args, expected.shape) is None
    np.testing.assert_array_equal(
        ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
    )
    assert len(cube_reads) == 3


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_an_unwritable_cache_dir_only_disables_filling(
    ops: OperationEDAXStateHandler,
    cache: ResultCache,
    cube: np.ndarray,
    cube_reads: list[tuple[int, int]],
) -> None:
    cache.cache_dir.mkdir()
    cache.cache_dir.chmod(0o500)
    try:
        expected = cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
        for _ in range(2):
            np.testing.assert_array_equal(
                ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
            )
        assert len(cube_reads) == 2
        assert not list(cache.cache_dir.iterdir())
    finally:
        cache.cache_dir.chmod(0o700)


def test_a_fileset_outside_the_data_root_is_never_cached(
    tmp_path: Path, ph: EDAXPathHandler, cube: np.ndarray
) -> None:
    elsewhere = ResultCache(tmp_path / "cache", tmp_path / "another_root")
    ops = OperationEDAXStateHandler(ph, result_cache=elsewhere)
    expected = cube[:, :, 10:30].sum(axis=-1, dtype=np.int64)
    np.testing.assert_array_equal(
        ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE), expected
    )
    assert not elsewhere.cache_dir.exists()


def test_mock_samples_are_not_cached(
    ops: OperationEDAXStateHandler, cache: ResultCache
) -> None:
    ops.get_multi_channel_intensity_image(_on_disc_mock.filenames[0], (0, 4))
    ops.get_spectrum(_on_disc_mock.filenames[0])
    assert not cache.cache_dir.exists()


def test_no_cache_without_the_setting(
    ph: EDAXPathHandler, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops = OperationEDAXStateHandler(ph)
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert not list(tmp_path.rglob("*.npz"))

    monkeypatch.chdir(tmp_path)
    get_result_cache.cache_clear()
    try:
        assert Settings().result_cache_dir is None
        assert get_result_cache() is None
    finally:
        get_result_cache.cache_clear()


def test_the_settings_are_read_from_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(f"{ENV_PREFIX}RESULT_CACHE_DIR='/srv/cache'\n")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.result_cache_dir == "/srv/cache"
    assert s.result_cache_fill is False

    get_settings.cache_clear()
    get_result_cache.cache_clear()
    try:
        cache = get_result_cache()
        assert cache is not None
        assert cache.fill is False
    finally:
        get_settings.cache_clear()
        get_result_cache.cache_clear()

    (tmp_path / ".env").write_text(
        f"{ENV_PREFIX}RESULT_CACHE_DIR='/srv/cache'\n{ENV_PREFIX}RESULT_CACHE_FILL=true\n"
    )
    assert Settings().result_cache_fill is True


def test_fill_off_makes_the_cache_read_only(
    ph: EDAXPathHandler,
    data_root: Path,
    tmp_path: Path,
    cube_reads: list[tuple[int, int]],
) -> None:
    writer = ResultCache(tmp_path / "cache", data_root)
    reader = ResultCache(tmp_path / "cache", data_root, fill=False)
    ops = OperationEDAXStateHandler(ph, result_cache=reader)

    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    ops.get_spectrum(SAMPLE)
    assert not reader.cache_dir.exists()

    # what the precompute script wrote is still served
    OperationEDAXStateHandler(ph, result_cache=writer).get_spectrum(SAMPLE)
    assert len(cube_reads) == 3
    ops.get_spectrum(SAMPLE)
    assert len(cube_reads) == 3


# ---------------------------------------------------------------------------
# the precompute script


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "precompute_result_cache", PRECOMPUTE_SCRIPT
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
    cache: ResultCache,
    ops: OperationEDAXStateHandler,
    cube_reads: list[tuple[int, int]],
) -> None:
    n_entries = 1 + len(DEFAULT_PRECOMPUTE_ELEMENTS)

    report = precompute_script.precompute(data_root, cache.cache_dir)
    assert (report.hits, report.writes, report.skipped_filesets) == (0, n_entries, 0)
    assert len(cube_reads) == n_entries
    assert len(list(cache.cache_dir.rglob("*.npz"))) == n_entries

    # re-running is cheap: every entry is up to date
    report = precompute_script.precompute(data_root, cache.cache_dir)
    assert (report.hits, report.writes, report.skipped_filesets) == (n_entries, 0, 0)
    assert len(cube_reads) == n_entries

    # the default view's requests are all hits
    channel_axis = ops.get_sample_axes(SAMPLE)[2]
    ops.get_spectrum(SAMPLE)
    for element in DEFAULT_PRECOMPUTE_ELEMENTS:
        window = element_energy_ranges_keV[element]
        ops.get_multi_channel_intensity_image(
            SAMPLE, channel_range_for_window(channel_axis, window)
        )
    assert len(cube_reads) == n_entries

    # a window the script did not image is still a miss
    ops.get_multi_channel_intensity_image(SAMPLE, CHANNEL_RANGE)
    assert len(cube_reads) == n_entries + 1


def test_script_elements_and_stamps(
    precompute_script: ModuleType,
    data_root: Path,
    ph: EDAXPathHandler,
    cache: ResultCache,
) -> None:
    report = precompute_script.precompute(data_root, cache.cache_dir, elements=("Fe",))
    assert (report.hits, report.writes) == (0, 2)

    _bump_mtime(_fileset(ph).spd)
    report = precompute_script.precompute(data_root, cache.cache_dir, elements=("Fe",))
    assert (report.hits, report.writes) == (0, 2)

    with pytest.raises(ValueError, match="no energy window for \\['Xx'\\]"):
        precompute_script.precompute(data_root, cache.cache_dir, elements=("Xx",))


def test_script_skips_a_fileset_it_cannot_read(
    precompute_script: ModuleType,
    data_root: Path,
    cache: ResultCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(_edax_files: EDAX_file_set) -> dict[str, Any]:
        msg = "unreadable header"
        raise OSError(msg)

    monkeypatch.setattr(file_loaders, "load_edax_spd_metadata", broken)
    report = precompute_script.precompute(data_root, cache.cache_dir)
    assert (report.hits, report.writes, report.skipped_filesets) == (0, 0, 1)


def test_script_honours_mixed_basenames(
    precompute_script: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "mixed_root"
    directory = root / "sample"
    directory.mkdir(parents=True)
    for name in ("map123_0.spd", "map123_0.spc", "map123_0.xml", "fov_1.ipr"):
        (directory / name).write_bytes(b"stub")
    cache_dir = tmp_path / "mixed_cache"

    report = precompute_script.precompute(root, cache_dir)
    assert report.writes == 0
    report = precompute_script.precompute(root, cache_dir, allow_mixed_basenames=True)
    assert report.writes == 1 + len(DEFAULT_PRECOMPUTE_ELEMENTS)
    assert (cache_dir / "sample" / "map123_0" / "spectrum.npz").is_file()


def test_script_main(
    precompute_script: ModuleType,
    data_root: Path,
    cache: ResultCache,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        precompute_script.main(
            [str(data_root), str(cache.cache_dir), "--elements", "Mg", "Si"]
        )
        == 0
    )
    assert "3 written" in capsys.readouterr().out
    shutil.rmtree(cache.cache_dir)


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

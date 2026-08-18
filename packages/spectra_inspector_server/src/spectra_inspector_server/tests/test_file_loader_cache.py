import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from spectra_inspector_server._testing import createEDAXMock
from spectra_inspector_server.model import EDAX_file_set
from spectra_inspector_server.processor import file_loaders


@pytest.fixture
def fileset(tmp_path: Path) -> EDAX_file_set:
    spd = tmp_path / "sample.spd"
    spd.write_bytes(b"not really an spd")
    return EDAX_file_set(spd=spd, spc=tmp_path / "s.spc", ipr=tmp_path / "s.ipr")


@pytest.fixture(autouse=True)
def edax_reader_calls(monkeypatch: pytest.MonkeyPatch) -> Generator[list[int]]:
    """count how often the (real) loaders would have been hit."""
    mock = createEDAXMock(im_shape=(4, 4, 3))
    calls: list[int] = []

    def fake_metadata(_edax_files: EDAX_file_set) -> dict[str, Any]:
        calls.append(1)
        return {
            "axes": [ax.model_dump() for ax in mock.axes],
            "metadata": mock.metadata,
            "original_metadata": mock.original_metadata,
        }

    monkeypatch.setattr(file_loaders, "load_edax_spd_metadata", fake_metadata)
    monkeypatch.setattr(
        file_loaders,
        "load_spd_into_memmap",
        lambda _header, _path: np.zeros((4, 4, 3), dtype=np.uint16),
    )
    file_loaders.clear_edax_cache()
    yield calls
    file_loaders.clear_edax_cache()


def test_repeated_loads_reuse_the_mapping(
    fileset: EDAX_file_set, edax_reader_calls: list[int]
) -> None:
    first = file_loaders.load_edax_spd(fileset)
    second = file_loaders.load_edax_spd(fileset)
    assert first is second
    assert len(edax_reader_calls) == 1


def test_metadata_only_is_cached_separately(fileset: EDAX_file_set) -> None:
    full = file_loaders.load_edax_spd(fileset)
    md_only = file_loaders.load_edax_spd(fileset, metadata_only=True)
    assert full.data is not None
    assert md_only.data is None
    assert file_loaders.load_edax_spd(fileset) is full


def test_a_rewritten_file_invalidates_the_cache(
    fileset: EDAX_file_set, edax_reader_calls: list[int]
) -> None:
    first = file_loaders.load_edax_spd(fileset)
    stat = fileset.spd.stat()
    fileset.spd.write_bytes(b"a different spd entirely")
    os.utime(fileset.spd, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))

    assert file_loaders.load_edax_spd(fileset) is not first
    assert len(edax_reader_calls) == 2


def test_cache_is_bounded(fileset: EDAX_file_set, tmp_path: Path) -> None:
    kept = file_loaders.load_edax_spd(fileset)
    for i in range(file_loaders._MAX_CACHED_FILESETS):
        spd = tmp_path / f"other{i}.spd"
        spd.write_bytes(b"x")
        other = EDAX_file_set(spd=spd, spc=spd, ipr=spd)
        file_loaders.load_edax_spd(other)

    assert len(file_loaders._ds_cache) == file_loaders._MAX_CACHED_FILESETS
    assert file_loaders.load_edax_spd(fileset) is not kept

import logging
from pathlib import Path

import pytest

from spectra_inspector_server._database.on_disk_db import get_expected_files
from spectra_inspector_server._file_tree_handling import EDAXPathHandler


def _write_edax_set(directory: Path, basename: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sample_file in get_expected_files(directory / (basename + ".spd")).values():
        sample_file.write_text(f"writing to {sample_file}")


@pytest.fixture
def root_with_duplicates(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "C-1")
    _write_edax_set(root / "session-a", "C-2")
    _write_edax_set(root / "session-b", "C-1")
    _write_edax_set(root / "session-b" / "nested", "C-1")
    return root


def test_duplicate_basename_warns_and_skips(
    root_with_duplicates: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        ph = EDAXPathHandler(root_with_duplicates, init_db=True)

    # the first C-1 encountered wins, the other two are skipped (which of the
    # three that is depends on directory iteration order)
    assert set(ph.database.available_maps) == {"C-1", "C-2"}
    assert ph.database.available_maps["C-1"].spd.name == "C-1.spd"

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    map_warnings = [w for w in warnings if "Duplicate map name" in w]
    assert len(map_warnings) == 2
    # each set's .spc is registered as a spectrum too, under the same rule
    spectrum_warnings = [w for w in warnings if "Duplicate spectrum name" in w]
    assert len(spectrum_warnings) == 2
    assert len(warnings) == 4


def test_duplicate_basename_in_working_directory(root_with_duplicates: Path) -> None:
    ph = EDAXPathHandler(root_with_duplicates, init_db=False)
    ph.set_working_directory(root_with_duplicates / "session-b")
    assert set(ph.database.available_maps) == {"C-1"}


def test_add_fileset_return_value(tmp_path: Path) -> None:
    _write_edax_set(tmp_path, "C-1")
    ph = EDAXPathHandler(tmp_path, init_db=False)
    files = get_expected_files(tmp_path / "C-1.spd")

    assert ph.database.add_fileset("C-1", files) is True
    assert ph.database.add_fileset("C-1", files) is False
    assert len(ph.database.available_maps) == 1

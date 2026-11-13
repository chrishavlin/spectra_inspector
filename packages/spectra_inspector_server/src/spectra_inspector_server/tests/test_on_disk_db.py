import logging
from pathlib import Path, PureWindowsPath

import pytest

from spectra_inspector_server._database.on_disk_db import (
    _mixed_basename_key,
    get_expected_files,
)
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


def test_mixed_basenames_key_relative_to_root_and_derive_sample(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "C-12 Map1")
    _write_edax_set(root / "session-a" / "nested", "C-12 Map2")
    ph = EDAXPathHandler(root, init_db=True, allow_mixed_basenames=True)

    # keyed by path relative to the data root, not the absolute server path
    assert set(ph.database.available_maps) == {
        "session-a/C-12 Map1.spd",
        "session-a/nested/C-12 Map2.spd",
    }
    assert set(ph.database.available_spectra) == {
        "session-a/C-12 Map1.spc",
        "session-a/nested/C-12 Map2.spc",
    }
    assert ph.database.available_maps["session-a/C-12 Map1.spd"].spd == (
        root / "session-a" / "C-12 Map1.spd"
    )
    # the sample id comes from the stem, so it matches the metadata csv
    assert ph.database.available_samples == {
        "session-a/C-12 Map1.spd": "C-12",
        "session-a/C-12 Map1.spc": "C-12",
        "session-a/nested/C-12 Map2.spd": "C-12",
        "session-a/nested/C-12 Map2.spc": "C-12",
    }


def test_mixed_basenames_working_directory_keys_relative_to_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "C-12 Map1")
    ph = EDAXPathHandler(root, init_db=False, allow_mixed_basenames=True)
    ph.set_working_directory(root / "session-a")

    assert set(ph.database.available_maps) == {"session-a/C-12 Map1.spd"}
    assert ph.database.available_samples["session-a/C-12 Map1.spd"] == "C-12"


def test_mixed_basename_key_is_posix_separated_on_windows() -> None:
    root = PureWindowsPath(r"C:\data_root")
    spd = root / "session-a" / "nested" / "C-12 Map2.spd"
    assert _mixed_basename_key(spd, root) == "session-a/nested/C-12 Map2.spd"


def test_dotted_basename_keeps_its_name_in_common_mode(tmp_path: Path) -> None:
    _write_edax_set(tmp_path, "C-1.v2 Map1")
    ph = EDAXPathHandler(tmp_path, init_db=True)

    assert ph.database.available_samples == {"C-1.v2 Map1": "C-1.v2"}

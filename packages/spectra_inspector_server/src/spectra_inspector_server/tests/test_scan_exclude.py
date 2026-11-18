import logging
from pathlib import Path

import pytest

from spectra_inspector_server._database.on_disk_db import get_expected_files
from spectra_inspector_server._database.scan_exclude import (
    ScanExclusions,
    load_scan_exclusions,
)
from spectra_inspector_server._file_browser import list_directory
from spectra_inspector_server._file_tree_handling import EDAXPathHandler

EXCLUDE = "scan_exclude.yaml"


def _write_edax_set(directory: Path, basename: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sample_file in get_expected_files(directory / (basename + ".spd")).values():
        sample_file.write_text(f"writing to {sample_file}")


def _write_exclude(root: Path, *patterns: str) -> None:
    body = "schema: 1\nexclude:\n" + "".join(f'  - "{p}"\n' for p in patterns)
    (root / EXCLUDE).write_text(body, encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "C-1")
    _write_edax_set(root / "session-a" / "nested", "C-2")
    _write_edax_set(root / "session-b", "C-3")
    _write_edax_set(root / "session-b", "C-4")
    return root


@pytest.mark.parametrize(
    ("pattern", "path", "excluded"),
    [
        ("session-a", "session-a", True),
        ("session-a/", "session-a/nested/C-2.spd", True),
        ("/session-a", "session-a/C-1.spd", True),
        ("session-a", "session-ab/C-1.spd", False),
        ("session-b/C-3.*", "session-b/C-3.spd", True),
        ("session-b/C-3.*", "session-b/C-3.ipr", True),
        ("session-b/C-3.*", "session-b/C-30.spd", False),
        # a wildcard stays inside its path segment
        ("*.spd", "top.spd", True),
        ("*.spd", "session-b/C-3.spd", False),
        ("session-*/C-?.spd", "session-b/C-3.spd", True),
        ("session-*/C-?.spd", "session-a/nested/C-2.spd", False),
        ("**/nested", "session-a/nested/C-2.spd", True),
        ("**/nested", "nested/C-2.spd", True),
        ("**/*.spd", "session-a/nested/C-2.spd", True),
        ("session-a/**", "session-a/nested/C-2.spd", True),
        ("session-a/**", "session-a", False),
        # no character classes: brackets are literal
        ("map [1].spd", "map [1].spd", True),
        ("map [1].spd", "map 1.spd", False),
        ("Session-A", "session-a/C-1.spd", False),
        # the .spc beside an excluded .spd goes with it
        ("session-b/C-3.spd", "session-b/C-3.spc", True),
        ("session-b/C-3.spd", "session-b/C-3.ipr", False),
        ("session-b/C-3.spc", "session-b/C-3.spd", False),
    ],
)
def test_pattern_matching(
    tmp_path: Path, pattern: str, path: str, excluded: bool
) -> None:
    exclusions = ScanExclusions(tmp_path, [pattern])
    assert exclusions.excludes(tmp_path / path) is excluded


def test_the_data_root_and_outside_paths_are_never_excluded(tmp_path: Path) -> None:
    root = tmp_path / "root"
    exclusions = ScanExclusions(root, ["*", "**"])
    assert not exclusions.excludes(root)
    assert not exclusions.excludes(tmp_path / "elsewhere" / "C-1.spd")
    assert exclusions.excludes(root / "anything")


def test_no_file_excludes_nothing(root: Path) -> None:
    ph = EDAXPathHandler(root, init_db=True)
    assert not ph.database.scan_exclusions
    assert set(ph.database.available_maps) == {"C-1", "C-2", "C-3", "C-4"}


@pytest.mark.parametrize("mixed", [False, True])
def test_excluded_directory_and_fileset_are_not_scanned(
    root: Path, mixed: bool
) -> None:
    _write_exclude(root, "session-a/nested", "session-b/C-3.*")
    ph = EDAXPathHandler(root, init_db=True, allow_mixed_basenames=mixed)

    if mixed:
        maps = {"session-a/C-1.spd", "session-b/C-4.spd"}
        spectra = {"session-a/C-1.spc", "session-b/C-4.spc"}
    else:
        maps = spectra = {"C-1", "C-4"}
    assert set(ph.database.available_maps) == maps
    assert set(ph.database.available_spectra) == spectra
    assert set(ph.database.available_samples) == maps | spectra


def test_excluding_the_spd_alone_leaves_no_spectrum_behind(root: Path) -> None:
    _write_exclude(root, "session-b/C-3.spd")
    ph = EDAXPathHandler(root, init_db=True)

    assert "C-3" not in ph.database.available_maps
    assert "C-3" not in ph.database.available_spectra


def test_exclusion_frees_a_duplicate_basename(root: Path) -> None:
    _write_edax_set(root / "session-c", "C-1")
    _write_exclude(root, "session-a/C-1.*")
    ph = EDAXPathHandler(root, init_db=True)

    assert ph.database.available_maps["C-1"].spd == root / "session-c" / "C-1.spd"


def test_refresh_rereads_the_file(root: Path) -> None:
    _write_exclude(root, "session-b")
    ph = EDAXPathHandler(root, init_db=True)
    assert set(ph.database.available_maps) == {"C-1", "C-2"}

    (root / EXCLUDE).unlink()
    ph.refresh()
    assert set(ph.database.available_maps) == {"C-1", "C-2", "C-3", "C-4"}


def test_working_directory_scan_applies_root_patterns(root: Path) -> None:
    _write_exclude(root, "session-a/nested", "session-b")
    ph = EDAXPathHandler(root, init_db=False)

    ph.set_working_directory(root / "session-a")
    assert set(ph.database.available_maps) == {"C-1"}

    # scanning straight into an excluded directory finds nothing
    ph.set_working_directory((root / "session-b").resolve())
    assert ph.database.available_maps == {}
    assert ph.database.available_spectra == {}


def test_browse_listing_hides_excluded_entries(root: Path) -> None:
    _write_exclude(root, "session-b", "session-a/C-1.*")
    exclusions = load_scan_exclusions(root)

    top = list_directory(root, exclusions=exclusions)
    assert [d.name for d in top.directories] == ["session-a"]

    session_a = list_directory(root, "session-a", exclusions=exclusions)
    assert [d.name for d in session_a.directories] == ["nested"]
    assert session_a.dataset_count == 0
    assert session_a.spectrum_count == 0

    session_b = list_directory(root, "session-b", exclusions=exclusions)
    assert session_b.directories == []
    assert session_b.dataset_count == 0


@pytest.mark.parametrize(
    "body",
    [
        "exclude: [unclosed",
        "exclude: not-a-list",
        "schema: 2\nexclude:\n  - session-a\n",
        "- just\n- a list\n",
    ],
)
def test_unreadable_file_is_ignored_with_a_warning(
    root: Path, body: str, caplog: pytest.LogCaptureFixture
) -> None:
    (root / EXCLUDE).write_text(body, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        ph = EDAXPathHandler(root, init_db=True)

    assert set(ph.database.available_maps) == {"C-1", "C-2", "C-3", "C-4"}
    assert "Ignoring scan exclude file" in caplog.text


@pytest.mark.parametrize("body", ["", "exclude:\n", "schema: 1\n", "other: 3\n"])
def test_empty_file_excludes_nothing(root: Path, body: str) -> None:
    (root / EXCLUDE).write_text(body, encoding="utf-8")
    assert not load_scan_exclusions(root)

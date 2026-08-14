from pathlib import Path

import pytest

from spectra_inspector_server._database.on_disk_db import get_expected_files
from spectra_inspector_server._file_browser import (
    PathOutsideRootError,
    list_directory,
    relative_to_root,
    resolve_within_root,
)
from spectra_inspector_server._file_tree_handling import EDAXPathHandler


def _write_edax_set(directory: Path, basename: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sample_file in get_expected_files(directory / (basename + ".spd")).values():
        sample_file.write_text(f"writing to {sample_file}")


@pytest.fixture
def browsable_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "C-1")
    _write_edax_set(root / "session-a" / "nested", "C-2")
    _write_edax_set(root / "session-b", "C-3")
    (root / ".hidden").mkdir()
    return root


def test_resolve_within_root_defaults_to_root(browsable_root: Path) -> None:
    assert resolve_within_root(browsable_root) == browsable_root.resolve()
    assert resolve_within_root(browsable_root, "") == browsable_root.resolve()
    assert resolve_within_root(browsable_root, ".") == browsable_root.resolve()


def test_resolve_within_root_relative(browsable_root: Path) -> None:
    resolved = resolve_within_root(browsable_root, "session-a/nested")
    assert resolved == (browsable_root / "session-a" / "nested").resolve()


def test_resolve_within_root_absolute_inside_root(browsable_root: Path) -> None:
    target = browsable_root / "session-b"
    assert resolve_within_root(browsable_root, str(target)) == target.resolve()


@pytest.mark.parametrize(
    "path",
    ["..", "../..", "session-a/../..", "/etc", "session-a/../../elsewhere"],
)
def test_resolve_within_root_rejects_escapes(browsable_root: Path, path: str) -> None:
    with pytest.raises(PathOutsideRootError, match="outside of the data root"):
        resolve_within_root(browsable_root, path)


def test_resolve_within_root_rejects_escaping_symlink(
    browsable_root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = browsable_root / "escape-hatch"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathOutsideRootError):
        resolve_within_root(browsable_root, "escape-hatch")


def test_relative_to_root(browsable_root: Path) -> None:
    assert relative_to_root(browsable_root, browsable_root.resolve()) == ""
    nested = (browsable_root / "session-a" / "nested").resolve()
    assert relative_to_root(browsable_root, nested) == "session-a/nested"


def test_list_directory_at_root(browsable_root: Path) -> None:
    listing = list_directory(browsable_root)

    assert listing.path == ""
    assert listing.parent_path is None
    assert listing.dataset_count == 0
    assert [d.name for d in listing.directories] == ["session-a", "session-b"]
    assert [d.path for d in listing.directories] == ["session-a", "session-b"]


def test_list_directory_reports_datasets_and_parent(browsable_root: Path) -> None:
    listing = list_directory(browsable_root, "session-a")

    assert listing.path == "session-a"
    assert listing.name == "session-a"
    assert listing.parent_path == ""
    assert listing.dataset_count == 1
    assert [d.path for d in listing.directories] == ["session-a/nested"]

    nested = list_directory(browsable_root, "session-a/nested")
    assert nested.parent_path == "session-a"
    assert nested.dataset_count == 1
    assert nested.directories == []


def test_list_directory_missing_path(browsable_root: Path) -> None:
    with pytest.raises(NotADirectoryError):
        list_directory(browsable_root, "not-a-real-directory")


def test_set_working_directory_recursive(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False)
    assert ph.database.available_maps == {}

    ph.set_working_directory(browsable_root / "session-a")
    assert set(ph.database.available_maps) == {"C-1", "C-2"}
    assert ph.working_directory == browsable_root / "session-a"


def test_set_working_directory_non_recursive(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False)

    ph.set_working_directory(browsable_root / "session-a", recursive=False)
    assert set(ph.database.available_maps) == {"C-1"}


def test_set_working_directory_replaces_previous(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False)

    ph.set_working_directory(browsable_root / "session-a")
    ph.set_working_directory(browsable_root / "session-b")

    assert set(ph.database.available_maps) == {"C-3"}
    # available_samples is cached, so it has to be invalidated alongside the maps
    assert set(ph.database.available_samples) == {"C-3"}


def test_set_working_directory_skips_duplicate_basenames(browsable_root: Path) -> None:
    # the same basename in two directories would raise on a plain scan
    _write_edax_set(browsable_root / "session-b" / "again", "C-3")

    ph = EDAXPathHandler(data_root=browsable_root, init_db=False)
    ph.set_working_directory(browsable_root / "session-b")

    assert set(ph.database.available_maps) == {"C-3"}


def test_set_working_directory_requires_a_directory(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False)
    with pytest.raises(NotADirectoryError):
        ph.set_working_directory(browsable_root / "session-a" / "C-1.spd")


def test_refresh_rescans_working_directory(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False)
    ph.set_working_directory(browsable_root / "session-b")
    assert set(ph.database.available_maps) == {"C-3"}

    _write_edax_set(browsable_root / "session-b", "C-4")
    ph.refresh()

    assert set(ph.database.available_maps) == {"C-3", "C-4"}
    # a refresh must not fall back to scanning the whole data root
    assert ph.working_directory == browsable_root / "session-b"


def test_max_datasets_stops_a_working_directory_scan(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False, max_datasets=1)

    # session-a holds C-1 directly and C-2 in a subdirectory
    ph.set_working_directory(browsable_root / "session-a")
    assert set(ph.database.available_maps) == {"C-1"}
    assert ph.database.scan_truncated is True


def test_scan_truncated_resets_between_selections(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False, max_datasets=2)

    ph.set_working_directory(browsable_root)
    assert ph.database.scan_truncated is True

    # session-b holds one dataset, comfortably under the cap
    ph.set_working_directory(browsable_root / "session-b")
    assert ph.database.scan_truncated is False


def test_max_datasets_stops_the_recursion_into_subdirectories(
    browsable_root: Path,
) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False, max_datasets=2)

    ph.set_working_directory(browsable_root)
    assert set(ph.database.available_maps) == {"C-1", "C-2"}


def test_max_datasets_above_the_dataset_count_is_a_noop(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False, max_datasets=100)

    ph.set_working_directory(browsable_root)
    assert set(ph.database.available_maps) == {"C-1", "C-2", "C-3"}


def test_max_datasets_survives_a_refresh(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=False, max_datasets=2)
    ph.set_working_directory(browsable_root)

    ph.refresh()
    assert set(ph.database.available_maps) == {"C-1", "C-2"}


def test_max_datasets_applies_to_a_startup_scan(browsable_root: Path) -> None:
    # the setting is only wired up in desktop mode (see dependencies.py), but
    # the database honors it wherever it is set.
    ph = EDAXPathHandler(data_root=browsable_root, init_db=True, max_datasets=1)
    assert set(ph.database.available_maps) == {"C-1"}


def test_working_directory_defaults_to_data_root(browsable_root: Path) -> None:
    ph = EDAXPathHandler(data_root=browsable_root, init_db=True)
    assert ph.working_directory == browsable_root
    assert set(ph.database.available_maps) == {"C-1", "C-2", "C-3"}

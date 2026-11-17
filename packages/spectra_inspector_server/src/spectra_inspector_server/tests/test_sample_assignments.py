import logging
import unicodedata
from pathlib import Path

import pytest

from spectra_inspector_server._database.on_disk_db import get_expected_files
from spectra_inspector_server._database.sample_assignments import (
    load_sample_assignments,
    normalize_key,
)
from spectra_inspector_server._file_tree_handling import EDAXPathHandler

ASSIGNMENTS = "sample_assignments.yaml"


def _write_edax_set(directory: Path, basename: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for sample_file in get_expected_files(directory / (basename + ".spd")).values():
        sample_file.write_text(f"writing to {sample_file}")


def _write_assignments(directory: Path, body: str) -> Path:
    path = directory / ASSIGNMENTS
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "oddly-named")
    _write_edax_set(root / "session-a", "C-12 Map1")
    return root


@pytest.mark.parametrize("mixed", [False, True])
def test_one_entry_resolves_in_both_key_modes(root: Path, mixed: bool) -> None:
    _write_assignments(
        root,
        'schema: 1\nmaps:\n  "session-a/oddly-named.spd":\n    sample: C-16\n'
        '    note: "free text"\n',
    )
    ph = EDAXPathHandler(root, init_db=True, allow_mixed_basenames=mixed)

    if mixed:
        expected = {
            "session-a/oddly-named.spd": "C-16",
            # the spectrum beside the map inherits the map's assignment
            "session-a/oddly-named.spc": "C-16",
            # unlisted names still go through the heuristic
            "session-a/C-12 Map1.spd": "C-12",
            "session-a/C-12 Map1.spc": "C-12",
        }
    else:
        expected = {"oddly-named": "C-16", "C-12 Map1": "C-12"}
    assert ph.database.available_samples == expected


def test_no_file_leaves_the_heuristic_alone(root: Path) -> None:
    ph = EDAXPathHandler(root, init_db=True)
    assert ph.database.sample_assignments_fullpath is None
    assert ph.database.available_samples == {
        "oddly-named": "oddly-named",
        "C-12 Map1": "C-12",
    }


def test_standalone_spectrum_is_keyed_by_its_spc(root: Path) -> None:
    (root / "loose").mkdir()
    (root / "loose" / "standard-check.spc").write_text("spc")
    _write_assignments(root, 'maps:\n  "loose/standard-check.spc":\n    sample: C-3\n')
    ph = EDAXPathHandler(root, init_db=True)

    assert ph.database.available_samples["standard-check"] == "C-3"


def test_spc_entry_wins_over_the_sibling_map_in_mixed_mode(root: Path) -> None:
    _write_assignments(
        root,
        "maps:\n"
        '  "session-a/oddly-named.spd":\n    sample: C-16\n'
        '  "session-a/oddly-named.spc":\n    sample: C-17\n',
    )
    ph = EDAXPathHandler(root, init_db=True, allow_mixed_basenames=True)

    samples = ph.database.available_samples
    assert samples["session-a/oddly-named.spd"] == "C-16"
    assert samples["session-a/oddly-named.spc"] == "C-17"


def test_key_spellings_are_normalized(root: Path) -> None:
    _write_edax_set(root / "session-a", "café")
    decomposed = unicodedata.normalize("NFD", "café")
    _write_assignments(
        root,
        "maps:\n"
        "  'session-a\\oddly-named.spd':\n    sample: C-16\n"
        '  "/session-a/C-12 Map1.spd":\n    sample: C-99\n'
        f'  "session-a/{decomposed}.spd":\n    sample: C-20\n',
    )
    ph = EDAXPathHandler(root, init_db=True)

    samples = ph.database.available_samples
    assert samples["oddly-named"] == "C-16"
    assert samples["C-12 Map1"] == "C-99"
    # the scan reports the name in whichever form the filesystem stores it
    assert {v for k, v in samples.items() if normalize_key(k) == "café"} == {"C-20"}


def test_entry_for_a_skipped_duplicate_does_not_reach_the_winner(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data_root"
    _write_edax_set(root / "session-a", "dup")
    _write_edax_set(root / "session-b", "dup")
    _write_assignments(root, 'maps:\n  "session-b/dup.spd":\n    sample: C-16\n')
    ph = EDAXPathHandler(root, init_db=True)

    # directories are walked in sorted order, so session-a's set is registered
    assert ph.database.available_maps["dup"].spd.parent.name == "session-a"
    assert ph.database.available_samples == {"dup": "dup"}


def test_working_directory_file_is_preferred_and_keys_stay_root_relative(
    root: Path,
) -> None:
    _write_assignments(root, 'maps:\n  "session-a/oddly-named.spd":\n    sample: C-1\n')
    ph = EDAXPathHandler(root, init_db=False)

    ph.set_working_directory(root / "session-a")
    assert ph.database.available_samples["oddly-named"] == "C-1"

    local = _write_assignments(
        root / "session-a",
        'maps:\n  "session-a/oddly-named.spd":\n    sample: C-2\n',
    )
    ph.set_working_directory(root / "session-a")
    assert ph.database.sample_assignments_fullpath == local
    assert ph.database.available_samples["oddly-named"] == "C-2"


def test_resolved_working_directory_under_a_symlinked_root(
    root: Path, tmp_path: Path
) -> None:
    link = tmp_path / "linked_root"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")
    _write_assignments(
        root, 'maps:\n  "session-a/oddly-named.spd":\n    sample: C-16\n'
    )
    ph = EDAXPathHandler(link, init_db=False)

    ph.set_working_directory((link / "session-a").resolve())
    assert ph.database.available_samples["oddly-named"] == "C-16"


def test_file_is_reread_on_refresh(root: Path) -> None:
    ph = EDAXPathHandler(root, init_db=True)
    assert ph.database.available_samples["oddly-named"] == "oddly-named"

    path = _write_assignments(
        root, 'maps:\n  "session-a/oddly-named.spd":\n    sample: C-16\n'
    )
    ph.refresh()
    assert ph.database.available_samples["oddly-named"] == "C-16"

    path.unlink()
    ph.refresh()
    assert ph.database.available_samples["oddly-named"] == "oddly-named"


def test_sample_missing_from_the_csv_warns_and_is_kept(
    root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    text_columns = [
        "group_name",
        "sample_type",
        "description",
        "gps",
        "location_notes",
        "gps_quality_note",
        "elevation_quality_note",
        "processing_note",
        "lat_str",
        "lon_str",
    ]
    header = ",".join(["sample_name", *text_columns, "elevation", "lat", "lon"])
    row = ",".join(["C-16", *("x" for _ in text_columns), "100.5", "1.0", "2.0"])
    (root / "sample_metadata.csv").write_text(f"{header}\n{row}\n")
    _write_assignments(
        root,
        "maps:\n"
        '  "session-a/oddly-named.spd":\n    sample: C-16\n'
        '  "session-a/C-12 Map1.spd":\n    sample: not-a-sample\n',
    )
    ph = EDAXPathHandler(root, init_db=True)

    with caplog.at_level(logging.WARNING):
        samples = ph.database.available_samples

    assert samples == {"oddly-named": "C-16", "C-12 Map1": "not-a-sample"}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "not-a-sample" in warnings[0]

    mapper = ph.database.sample_metadata_mapper
    assert mapper is not None
    meta = mapper.get_all(available_samples=samples)
    assert meta.map_samples == samples


@pytest.mark.parametrize(
    "body",
    [
        "maps: [not, a, mapping",
        "schema: 2\nmaps: {}\n",
        'maps:\n  "session-a/oddly-named.spd": C-16\n',
        'maps:\n  "session-a/oddly-named.spd":\n    note: no sample\n',
        "- just\n- a list\n",
    ],
)
def test_unreadable_file_is_ignored_with_a_warning(
    root: Path, body: str, caplog: pytest.LogCaptureFixture
) -> None:
    _write_assignments(root, body)
    with caplog.at_level(logging.WARNING):
        ph = EDAXPathHandler(root, init_db=True)

    assert ph.database.available_samples["oddly-named"] == "oddly-named"
    assert any(ASSIGNMENTS in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("body", ["", "maps:\n", "schema: 1\n"])
def test_empty_file_loads_as_no_assignments(tmp_path: Path, body: str) -> None:
    assert load_sample_assignments(_write_assignments(tmp_path, body)) == {}


def test_unknown_fields_are_ignored(tmp_path: Path) -> None:
    path = _write_assignments(
        tmp_path,
        "schema: 1\nfuture: thing\nmaps:\n"
        '  "a/b.spd":\n    sample: 12\n    source: curated\n'
        "    fingerprint: sha256:ab12\n",
    )
    assert load_sample_assignments(path) == {"a/b.spd": "12"}

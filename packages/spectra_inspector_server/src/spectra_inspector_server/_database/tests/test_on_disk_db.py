from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from spectra_inspector_server._database.on_disk_db import (
    find_edax_datasets_common_basename,
    find_edax_datasets_mixed_basename,
    get_expected_files,
)
from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server.processor.utilities import _map_to_sample_name

if TYPE_CHECKING:
    from spectra_inspector_server.model import EDAX_file_set

import pandas as pd


@pytest.fixture
def on_disk_path(tmp_path: Path) -> tuple[Path, list[str]]:
    # build a test db on disk: this could be a useful fixture
    db_root = tmp_path / "top_db"
    assert isinstance(db_root, Path)
    db_root.mkdir()

    annoying_directory = "annoying second level with spaces"

    sample_names = ["C-1", "C-2", "C-45 Map 1", "whatever-you-want"]
    for sample in sample_names:
        sample_dir = db_root / sample
        sample_dir.mkdir()

        sub_dir = sample_dir / annoying_directory
        sub_dir.mkdir()

        spd_base = sample + ".spd"
        spd_file = sub_dir / spd_base

        sample_files: dict[str, Path] = get_expected_files(spd_file)
        for sample_file in sample_files.values():
            # write the .spd, .ipr, etc.
            with open(str(sample_file), "w") as fh:
                fh.write(f"writing to {sample_file}")

    # add one more in an existing directory
    new_samp = "lets-make-another-sample"
    sample_names.append(new_samp)
    spd_file = db_root / "C-1" / annoying_directory / (new_samp + ".spd")
    observed_sample_files: dict[str, Path] = get_expected_files(spd_file)
    for sample_file in observed_sample_files.values():
        with open(str(sample_file), "w") as fh:
            fh.write(f"writing to {sample_file}")

    return db_root, sample_names


def test_on_disk_db_init(on_disk_path: tuple[Path, list[str]]) -> None:

    db_root, sample_names = on_disk_path

    ph = EDAXPathHandler(data_root=db_root, init_db=True)

    for _ in range(2):
        maps: dict[str, EDAX_file_set] = ph.database.available_maps
        assert set(maps.keys()) == set(sample_names)

        for sample_set in maps.values():
            assert sample_set.bmp
            assert sample_set.bmp.exists()
            assert sample_set.spd.exists()
            assert sample_set.spc.exists()
            assert sample_set.ipr.exists()
            assert sample_set.xml
            assert sample_set.xml.exists()

        ph.refresh()


def test_map_to_sample_id(on_disk_path: tuple[Path, list[str]]) -> None:
    db_root, sample_names = on_disk_path

    csv_fi = db_root / "sample_metadata.csv"

    data_records = [_fake_record(sample_name) for sample_name in sample_names]
    df = pd.DataFrame(data_records)
    df.to_csv(csv_fi, index=False)

    assert csv_fi.is_file()

    ph = EDAXPathHandler(data_root=db_root, init_db=True)
    assert ph.database.sample_metadata_fullpath is not None
    assert ph.database.sample_metadata_fullpath.is_file()

    assert ph.database.sample_metadata_mapper is not None
    smd = ph.database.sample_metadata_mapper.get_all()
    assert smd.records is not None
    assert len(smd.records) == len(sample_names)
    assert smd.map_samples is None

    available_samples = ph.database.available_samples

    smd = ph.database.sample_metadata_mapper.get_all(
        available_samples=available_samples
    )
    assert smd.map_samples
    for sn in sample_names:
        assert sn in smd.map_samples


def _fake_record(sample_name: str) -> dict[str, str | float]:
    rec: dict[str, str | float] = {
        "sample_name": _map_to_sample_name(sample_name),
    }

    str_cols = [
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
    for col in str_cols:
        rec[col] = "random string " + col

    rec["elevation"] = 100.5
    rec["lat"] = 50.2
    rec["lon"] = 120.1
    return rec


def touch(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).touch()


def test_mixed_basename_single_dataset(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "fov1.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(tmp_path)

    assert len(datasets) == 1

    ds = datasets[0]
    assert ds.spd.name == "map123_0.spd"
    assert ds.spc.name == "map123_0.spc"
    assert ds.xml is not None
    assert ds.xml.name == "map123_0.xml"
    assert ds.ipr.name == "fov1.ipr"
    assert ds.bmp is not None
    assert ds.bmp.name == "fov1.bmp"


def test_mixed_basename_multiple_datasets(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "fov1.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
        "map456_0.spd",
        "map456_0.spc",
        "map456_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(tmp_path)

    assert len(datasets) == 2
    assert [d.spd.stem for d in datasets] == [
        "map123_0",
        "map456_0",
    ]

    assert all(d.ipr.name == "fov1.ipr" for d in datasets)
    for d in datasets:
        assert d.bmp is not None
        assert d.bmp.name == "fov1.bmp"


def test_mixed_basename_missing_ipr_returns_empty(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    assert find_edax_datasets_mixed_basename(tmp_path) == []


def test_mixed_basename_incomplete_map_set_ignored(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "fov1.bmp",
        "map123_0.spd",
        "map123_0.spc",
        # xml missing
    )

    assert find_edax_datasets_mixed_basename(tmp_path) == []


def test_mixed_basename_complete_and_incomplete_sets(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "fov1.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
        "map456_0.spd",
        "map456_0.spc",
        # xml missing
    )

    datasets = find_edax_datasets_mixed_basename(tmp_path)

    assert len(datasets) == 1
    assert datasets[0].spd.stem == "map123_0"


def test_mixed_basename_first_fov_selected(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov001.ipr",
        "fov001.bmp",
        "fov999.ipr",
        "fov999.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    ds = find_edax_datasets_mixed_basename(tmp_path)[0]

    assert ds.ipr.name == "fov001.ipr"
    assert ds.bmp is not None
    assert ds.bmp.name == "fov001.bmp"


def test_mixed_basename_missing_bmp_is_allowed(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    ds = find_edax_datasets_mixed_basename(tmp_path)[0]
    assert ds.bmp is None


def test_mixed_basename_unrelated_files_ignored(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "fov1.bmp",
        "notes.txt",
        "junk.xml",
        "image.png",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(tmp_path)
    assert len(datasets) == 1


def test_common_basename_single_dataset(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.spc",
        "sample.ipr",
        "sample.xml",
        "sample.bmp",
    )

    datasets = find_edax_datasets_common_basename(tmp_path)

    assert len(datasets) == 1

    ds = datasets[0]
    assert ds.spd.name == "sample.spd"
    assert ds.spc.name == "sample.spc"
    assert ds.ipr.name == "sample.ipr"

    assert ds.xml is not None
    assert ds.xml.name == "sample.xml"

    assert ds.bmp is not None
    assert ds.bmp.name == "sample.bmp"


def test_mixed_basename_custom_map_prefix(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "fov1.bmp",
        "scan123_0.spd",
        "scan123_0.spc",
        "scan123_0.xml",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(
        tmp_path,
        map_prefix="scan",
    )

    assert len(datasets) == 1

    ds = datasets[0]
    assert ds.spd.name == "scan123_0.spd"
    assert ds.spc.name == "scan123_0.spc"

    assert ds.xml is not None
    assert ds.xml.name == "scan123_0.xml"


def test_mixed_basename_custom_fov_prefix(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "image1.ipr",
        "image1.bmp",
        "fov1.ipr",
        "fov1.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(
        tmp_path,
        fov_prefix="image",
    )

    assert len(datasets) == 1

    ds = datasets[0]

    assert ds.ipr.name == "image1.ipr"

    assert ds.bmp is not None
    assert ds.bmp.name == "image1.bmp"


def test_mixed_basename_custom_map_and_fov_prefix(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "image001.ipr",
        "image001.bmp",
        "scanABC_0.spd",
        "scanABC_0.spc",
        "scanABC_0.xml",
        "mapABC_0.spd",
        "mapABC_0.spc",
        "mapABC_0.xml",
        "fov001.ipr",
        "fov001.bmp",
    )

    datasets = find_edax_datasets_mixed_basename(
        tmp_path,
        map_prefix="scan",
        fov_prefix="image",
    )

    assert len(datasets) == 1

    ds = datasets[0]

    assert ds.spd.name == "scanABC_0.spd"
    assert ds.spc.name == "scanABC_0.spc"
    assert ds.ipr.name == "image001.ipr"

    assert ds.xml is not None
    assert ds.xml.name == "scanABC_0.xml"

    assert ds.bmp is not None
    assert ds.bmp.name == "image001.bmp"


def test_mixed_basename_wrong_map_prefix_returns_empty(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "fov1.ipr",
        "fov1.bmp",
        "scan123_0.spd",
        "scan123_0.spc",
        "scan123_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(
        tmp_path,
        map_prefix="map",
    )

    assert datasets == []


def test_mixed_basename_wrong_fov_prefix_returns_empty(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "image1.ipr",
        "image1.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(
        tmp_path,
        fov_prefix="fov",
    )

    assert datasets == []


def test_mixed_basename_custom_prefix_selects_first_matching_fov(
    tmp_path: Path,
) -> None:
    touch(
        tmp_path,
        "image002.ipr",
        "image002.bmp",
        "image001.ipr",
        "image001.bmp",
        "map123_0.spd",
        "map123_0.spc",
        "map123_0.xml",
    )

    datasets = find_edax_datasets_mixed_basename(
        tmp_path,
        fov_prefix="image",
    )

    assert len(datasets) == 1

    ds = datasets[0]

    assert ds.ipr.name == "image001.ipr"

    assert ds.bmp is not None
    assert ds.bmp.name == "image001.bmp"


def test_common_basename_multiple_datasets(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "alpha.spd",
        "alpha.spc",
        "alpha.ipr",
        "alpha.xml",
        "alpha.bmp",
        "beta.spd",
        "beta.spc",
        "beta.ipr",
        "beta.xml",
        "beta.bmp",
    )

    datasets = find_edax_datasets_common_basename(tmp_path)

    assert len(datasets) == 2
    assert [d.spd.stem for d in datasets] == ["alpha", "beta"]


def test_common_basename_missing_ipr_ignored(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.spc",
        "sample.xml",
        "sample.bmp",
    )

    assert find_edax_datasets_common_basename(tmp_path) == []


def test_common_basename_missing_spd_ignored(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spc",
        "sample.ipr",
        "sample.xml",
        "sample.bmp",
    )

    assert find_edax_datasets_common_basename(tmp_path) == []


def test_common_basename_missing_spc_ignored(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.ipr",
        "sample.xml",
        "sample.bmp",
    )

    assert find_edax_datasets_common_basename(tmp_path) == []


def test_common_basename_xml_optional(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.spc",
        "sample.ipr",
        "sample.bmp",
    )

    datasets = find_edax_datasets_common_basename(tmp_path)

    assert len(datasets) == 1

    ds = datasets[0]
    assert ds.xml is None

    assert ds.bmp is not None
    assert ds.bmp.name == "sample.bmp"


def test_common_basename_bmp_optional(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.spc",
        "sample.ipr",
        "sample.xml",
    )

    datasets = find_edax_datasets_common_basename(tmp_path)

    assert len(datasets) == 1

    ds = datasets[0]

    assert ds.bmp is None

    assert ds.xml is not None
    assert ds.xml.name == "sample.xml"


def test_common_basename_xml_and_bmp_optional(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.spc",
        "sample.ipr",
    )

    datasets = find_edax_datasets_common_basename(tmp_path)

    assert len(datasets) == 1

    ds = datasets[0]
    assert ds.xml is None
    assert ds.bmp is None


def test_common_basename_mixed_basenames_not_matched(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.spc",
        "other.ipr",
        "sample.xml",
        "sample.bmp",
    )

    assert find_edax_datasets_common_basename(tmp_path) == []


def test_common_basename_complete_and_incomplete_sets(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "alpha.spd",
        "alpha.spc",
        "alpha.ipr",
        "alpha.xml",
        "alpha.bmp",
        "beta.spd",
        "beta.spc",
        # beta.ipr missing
        "beta.xml",
        "beta.bmp",
    )

    datasets = find_edax_datasets_common_basename(tmp_path)

    assert len(datasets) == 1
    assert datasets[0].spd.stem == "alpha"


def test_common_basename_unrelated_files_ignored(tmp_path: Path) -> None:
    touch(
        tmp_path,
        "sample.spd",
        "sample.spc",
        "sample.ipr",
        "sample.xml",
        "sample.bmp",
        "notes.txt",
        "image.png",
        "map123_0.spd",
        "junk.xml",
    )

    datasets = find_edax_datasets_common_basename(tmp_path)

    assert len(datasets) == 1
    assert datasets[0].spd.stem == "sample"

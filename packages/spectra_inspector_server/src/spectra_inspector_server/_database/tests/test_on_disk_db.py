from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from spectra_inspector_server._database.on_disk_db import _get_expected_files
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

        sample_files: dict[str, Path] = _get_expected_files(spd_file)
        for sample_file in sample_files.values():
            # write the .spd, .ipr, etc.
            with open(str(sample_file), "w") as fh:
                fh.write(f"writing to {sample_file}")

    # add one more in an existing directory
    new_samp = "lets-make-another-sample"
    sample_names.append(new_samp)
    spd_file = db_root / "C-1" / annoying_directory / (new_samp + ".spd")
    observed_sample_files: dict[str, Path] = _get_expected_files(spd_file)
    for sample_file in observed_sample_files.values():
        with open(str(sample_file), "w") as fh:
            fh.write(f"writing to {sample_file}")

    return db_root, sample_names


def test_on_disk_db_init(on_disk_path: tuple[Path, list[str]]) -> None:

    db_root, sample_names = on_disk_path

    ph = EDAXPathHandler(data_root=db_root, init_db=True)

    maps: dict[str, EDAX_file_set] = ph.database.available_maps
    assert set(maps.keys()) == set(sample_names)

    for sample_set in maps.values():
        assert sample_set.bmp.exists()
        assert sample_set.spd.exists()
        assert sample_set.spc.exists()
        assert sample_set.ipr.exists()
        assert sample_set.xml.exists()


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

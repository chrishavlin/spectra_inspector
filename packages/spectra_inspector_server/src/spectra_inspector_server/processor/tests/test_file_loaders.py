import struct
from pathlib import Path

import numpy as np

from spectra_inspector_server.model import EDAX_file_set
from spectra_inspector_server.processor.file_loaders import (
    load_edax_spd,
    parse_ipr_header,
    parse_spd_header,
)


def _write_spd_file(path: Path) -> None:
    tag = b"MAPSPECTRA_DATA"
    version = 1
    n_spectra = 1
    n_points = 2
    n_lines = 3
    n_channels = 4
    count_bytes = 2
    data_offset = 1024
    n_frames = 0
    file_name = b"test_map.bmp"
    filler = b"\x00" * 856

    header = struct.pack(
        "<16s8i120s856s",
        tag,
        version,
        n_spectra,
        n_points,
        n_lines,
        n_channels,
        count_bytes,
        data_offset,
        n_frames,
        file_name,
        filler,
    )
    assert len(header) == 1024
    path.write_bytes(header + b"\x00" * (data_offset - len(header)))
    data = np.arange(n_points * n_lines * n_channels, dtype="u2")
    with path.open("ab") as fh:
        fh.write(data.tobytes())


def _write_ipr_file(path: Path) -> None:
    dtype = np.dtype(
        [
            ("version", "<u2"),
            ("imageType", "<u2"),
            ("label", "S8"),
            ("sMin", "<u2"),
            ("sMax", "<u2"),
            ("color", "<u2"),
            ("presetMode", "<u2"),
            ("presetTime", "<u4"),
            ("dataType", "<u2"),
            ("timeConstantOld", "<u2"),
            ("reserved1", "<i2"),
            ("roiStartChan", "<u2"),
            ("roiEndChan", "<u2"),
            ("userMin", "<i2"),
            ("userMax", "<i2"),
            ("iADC", "<u2"),
            ("reserved2", "<i2"),
            ("iBits", "<u2"),
            ("nReads", "<u2"),
            ("nFrames", "<u2"),
            ("fDwell", "<f4"),
            ("accV", "<u2"),
            ("tilt", "<i2"),
            ("takeoff", "<i2"),
            ("mag", "<u4"),
            ("wd", "<u2"),
            ("mppX", "<f4"),
            ("mppY", "<f4"),
            ("nTextLines", "<u2"),
            ("charText", "4S32"),
            ("reserved3", "<4f4"),
            ("nOverlayElements", "<u2"),
            ("overlayColors", "<16u2"),
            ("timeConstantNew", "<f4"),
            ("reserved4", "<2f4"),
        ]
    )
    header = np.zeros(1, dtype=dtype)
    header["version"] = 334
    header["imageType"] = 2
    header["label"] = b"testimg"
    header["sMin"] = 0
    header["sMax"] = 100
    header["color"] = 0
    header["presetMode"] = 0
    header["presetTime"] = 0
    header["dataType"] = 1
    header["timeConstantOld"] = 0
    header["reserved1"] = 0
    header["roiStartChan"] = 0
    header["roiEndChan"] = 0
    header["userMin"] = 0
    header["userMax"] = 0
    header["iADC"] = 1
    header["reserved2"] = 0
    header["iBits"] = 8
    header["nReads"] = 1
    header["nFrames"] = 1
    header["fDwell"] = 0.0
    header["accV"] = 0
    header["tilt"] = 0
    header["takeoff"] = 0
    header["mag"] = 1
    header["wd"] = 1
    header["mppX"] = 0.25
    header["mppY"] = 0.30
    header["nTextLines"] = 2
    header["charText"] = (
        b"line one" + b"\x00" * 25,
        b"line two" + b"\x00" * 25,
        b"",
        b"",
    )
    header["reserved3"] = (0.0, 0.0, 0.0, 0.0)
    header["nOverlayElements"] = 0
    header["overlayColors"] = tuple([0] * 16)
    header["timeConstantNew"] = 0.0
    header["reserved4"] = (0.0, 0.0)
    path.write_bytes(header.tobytes())


def test_parse_spd_and_ipr_headers(tmp_path: Path) -> None:
    spd_path = tmp_path / "sample.spd"
    ipr_path = tmp_path / "sample.ipr"
    _write_spd_file(spd_path)
    _write_ipr_file(ipr_path)

    spd_header = parse_spd_header(spd_path)
    ipr_header = parse_ipr_header(ipr_path)

    assert spd_header["tag"] == "MAPSPECTRA_DATA"
    assert spd_header["nPoints"] == 2
    assert spd_header["nLines"] == 3
    assert spd_header["nChannels"] == 4
    assert spd_header["dataOffset"] == 1024
    assert ipr_header["mppX"] == 0.25
    assert np.isclose(ipr_header["mppY"], 0.30)
    assert ipr_header["charText"] == ["line one", "line two", "", ""]


def test_load_edax_spd_reads_local_headers(tmp_path: Path) -> None:
    spd_path = tmp_path / "sample.spd"
    ipr_path = tmp_path / "sample.ipr"
    _write_spd_file(spd_path)
    _write_ipr_file(ipr_path)

    edax_files = EDAX_file_set(
        spd=spd_path,
        spc=tmp_path / "sample.spc",
        ipr=ipr_path,
        bmp=tmp_path / "sample.bmp",
        xml=tmp_path / "sample.xml",
    )
    ds = load_edax_spd(edax_files, metadata_only=False)

    assert ds.data is not None
    assert ds.data.shape == (3, 2, 4)
    assert ds.original_metadata["spd_header"]["tag"] == "MAPSPECTRA_DATA"
    assert ds.original_metadata["ipr_header"]["mppX"] == 0.25
    assert np.isclose(ds.original_metadata["ipr_header"]["mppY"], 0.30)

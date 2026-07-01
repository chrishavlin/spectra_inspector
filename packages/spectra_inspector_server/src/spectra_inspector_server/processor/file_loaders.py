from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from spectra_inspector_server.model import EDAX_file_set, EDAX_raw_ds


def _decode_string(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("latin-1").rstrip("\x00")
    if isinstance(value, np.bytes_):
        return value.decode("latin-1").rstrip("\x00")
    return str(value)


def parse_spd_header(spd_path: str | Path) -> dict[str, Any]:
    with Path(spd_path).open("rb") as fh:
        header = np.fromfile(
            fh,
            dtype=[
                ("tag", "S16"),
                ("version", "<i4"),
                ("nSpectra", "<i4"),
                ("nPoints", "<i4"),
                ("nLines", "<u4"),
                ("nChannels", "<u4"),
                ("countBytes", "<u4"),
                ("dataOffset", "<u4"),
                ("nFrames", "<u4"),
                ("fName", "S120"),
                ("filler", "V900"),
            ],
            count=1,
        )

    values = header[0]
    return {
        "tag": _decode_string(values["tag"]),
        "version": int(values["version"]),
        "nSpectra": int(values["nSpectra"]),
        "nPoints": int(values["nPoints"]),
        "nLines": int(values["nLines"]),
        "nChannels": int(values["nChannels"]),
        "countBytes": int(values["countBytes"]),
        "dataOffset": int(values["dataOffset"]),
        "nFrames": int(values["nFrames"]),
        "fName": _decode_string(values["fName"]),
    }


def parse_ipr_header(ipr_path: str | Path) -> dict[str, Any]:
    with Path(ipr_path).open("rb") as fh:
        version = np.fromfile(fh, dtype=[("version", "<u2")], count=1)[0]["version"]
        fh.seek(0)

        dtype_list: list[tuple[str, str]] = [
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
        ]
        if int(version) >= 334:
            dtype_list.extend([("timeConstantNew", "<f4"), ("reserved4", "<2f4")])

        header = np.fromfile(fh, dtype=dtype_list, count=1)[0]

    values: dict[str, Any] = {
        "version": int(header["version"]),
        "imageType": int(header["imageType"]),
        "label": _decode_string(header["label"]),
        "sMin": int(header["sMin"]),
        "sMax": int(header["sMax"]),
        "color": int(header["color"]),
        "presetMode": int(header["presetMode"]),
        "presetTime": int(header["presetTime"]),
        "dataType": int(header["dataType"]),
        "timeConstantOld": int(header["timeConstantOld"]),
        "roiStartChan": int(header["roiStartChan"]),
        "roiEndChan": int(header["roiEndChan"]),
        "userMin": int(header["userMin"]),
        "userMax": int(header["userMax"]),
        "iADC": int(header["iADC"]),
        "iBits": int(header["iBits"]),
        "nReads": int(header["nReads"]),
        "nFrames": int(header["nFrames"]),
        "fDwell": float(header["fDwell"]),
        "accV": int(header["accV"]),
        "tilt": int(header["tilt"]),
        "takeoff": int(header["takeoff"]),
        "mag": int(header["mag"]),
        "wd": int(header["wd"]),
        "mppX": float(header["mppX"]),
        "mppY": float(header["mppY"]),
        "nTextLines": int(header["nTextLines"]),
        "charText": [_decode_string(text) for text in header["charText"]],
    }

    if int(version) >= 334:
        values["timeConstantNew"] = float(header["timeConstantNew"])

    return values


def load_edax_spd_metadata(edax_files: EDAX_file_set) -> dict[str, Any]:
    spd_header = parse_spd_header(edax_files.spd)
    ipr_header = parse_ipr_header(edax_files.ipr)

    axes = [
        {
            "size": spd_header["nLines"],
            "index_in_array": 0,
            "name": "y",
            "scale": ipr_header.get("mppY", 1.0),
            "offset": 0,
            "units": "µm" if "mppY" in ipr_header else "",
            "navigate": True,
        },
        {
            "size": spd_header["nPoints"],
            "index_in_array": 1,
            "name": "x",
            "scale": ipr_header.get("mppX", 1.0),
            "offset": 0,
            "units": "µm" if "mppX" in ipr_header else "",
            "navigate": True,
        },
        {
            "size": spd_header["nChannels"],
            "index_in_array": 2,
            "name": "Energy",
            "scale": 1.0,
            "offset": 0,
            "units": "",
            "navigate": False,
        },
    ]

    metadata = {
        "General": {
            "original_filename": edax_files.spd.name,
            "title": "EDS Spectrum Image",
        },
        "Signal": {"signal_type": "EDS_SEM"},
    }

    return {
        "axes": axes,
        "metadata": metadata,
        "original_metadata": {
            "spd_header": spd_header,
            "ipr_header": ipr_header,
        },
    }


def load_spd_into_memmap(
    header: dict[str, Any], spd_path: str | Path
) -> npt.NDArray[np.int64]:
    nx = header["nPoints"]
    ny = header["nLines"]
    nCh = header["nChannels"]
    offset = header["dataOffset"]
    nbytes = str(header["countBytes"])
    data_type = {"1": "u1", "2": "u2", "4": "u4"}[nbytes]

    with Path(spd_path).open("rb") as f:
        data: npt.NDArray[np.int64] = np.memmap(
            f, mode="r", offset=offset, dtype=data_type
        )  # type: ignore[call-overload]
    data = data.squeeze().reshape((nCh, nx, ny), order="F").T
    return data


def load_edax_spd(
    edax_files: EDAX_file_set, metadata_only: bool = False
) -> EDAX_raw_ds:
    md = load_edax_spd_metadata(edax_files)
    if metadata_only:
        return EDAX_raw_ds(md)
    data = load_spd_into_memmap(md["original_metadata"]["spd_header"], edax_files.spd)
    md.update({"data": data})
    return EDAX_raw_ds(md)


def find_data_start(msa_path: str) -> int:
    idx = 0
    with open(msa_path) as fh:
        while True:
            idx += 1
            msa_data = fh.readline()
            if "Spectral Data Starts Here" in msa_data:
                return idx
            if idx > 100:
                msg = "Could not identify starting row for msa data"
                raise RuntimeError(msg)


def load_msa(msa_path: str) -> pd.DataFrame:
    # Note: rosetasciio supports "Y" and "XY" formats, this loader assumes "XY".
    # TODO: handle "Y", also save the metadata.
    idx = find_data_start(msa_path)
    # engine='python' to avoid warning using skipfooter
    return pd.read_csv(
        msa_path,
        skiprows=idx,
        header=None,
        names=["x", "intensity"],
        skipfooter=1,
        engine="python",
    )

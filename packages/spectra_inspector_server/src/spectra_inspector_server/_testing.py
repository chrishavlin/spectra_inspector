import os
from collections import OrderedDict

import numpy as np

from spectra_inspector_server.model import EDAX_raw_ds


def createEDAXMock(im_shape: tuple[int, int, int] | None = None) -> EDAX_raw_ds:

    if im_shape is None:
        im_shape = (16, 16, 10)

    nLines = im_shape[0]
    nPoints = im_shape[1]
    nChannels = im_shape[2]
    nSpectra = np.prod(im_shape).astype(int)

    fake_raw_ds = {}
    axes = []
    axes.append(
        {
            "size": im_shape[0],
            "index_in_array": 0,
            "name": "y",
            "scale": np.float32(1.5876777),
            "offset": 0,
            "units": "µm",
            "navigate": True,
        }
    )
    axes.append(
        {
            "size": im_shape[1],
            "index_in_array": 1,
            "name": "x",
            "scale": np.float32(1.6013774),
            "offset": 0,
            "units": "µm",
            "navigate": True,
        }
    )
    axes.append(
        {
            "size": im_shape[2],
            "index_in_array": 2,
            "name": "Energy",
            "scale": np.float64(0.005),
            "offset": np.float32(0.0),
            "units": "keV",
            "navigate": False,
        }
    )
    fake_raw_ds["axes"] = axes

    rng = np.random.default_rng()
    fkdata = rng.random(im_shape) * 10
    fake_raw_ds["data"] = fkdata.astype(np.int64)  # type:ignore[assignment]
    fake_raw_ds["metadata"] = {
        "General": {"original_filename": "C-12.spd", "title": "EDS Spectrum Image"},
        "Signal": {"signal_type": "EDS_SEM"},
        "Acquisition_instrument": {
            "SEM": {
                "Detector": {
                    "EDS": {
                        "azimuth_angle": np.float32(0.0),
                        "elevation_angle": np.float32(33.5),
                        "energy_resolution_MnKa": np.float32(125.19505),
                        "live_time": np.float32(3276.8),
                    }
                },
                "beam_energy": np.float32(15.0),
                "Stage": {"tilt_alpha": np.float32(0.0)},
            }
        },
        "Sample": {"elements": ["Al", "Ca", "Fe", "K", "Mg", "Na", "O", "Si"]},
    }  # type:ignore[assignment]

    # note: the original metadata here is mostly copied from the C-12
    # data. The "filler" entries were long byte-strings stored in np.void arrays,
    # they are replaced here with np.void(b'bytesfiller')
    # only other modifications are related to the dimensions. changing the dimensions
    # will likely invalidate some of the offsets, etc in the metadata, but good enough
    # for a mock ds.

    orig_metadata = {}
    spd_h = OrderedDict(
        {
            "tag": np.bytes_(b"MAPSPECTRA_DATA"),
            "version": np.int32(1001),
            "nSpectra": np.int32(nSpectra),
            "nPoints": np.int32(nPoints),
            "nLines": np.uint32(nLines),
            "nChannels": np.uint32(nChannels),
            "countBytes": np.uint32(1),
            "dataOffset": np.uint32(1068),
            "nFrames": np.uint32(20),
            "fName": np.bytes_(b"map20250805121843003_0_Img.bmp"),
            "filler": np.void(b"bytesfiller"),
        }
    )
    orig_metadata["spd_header"] = spd_h
    ipr_h = OrderedDict(
        {
            "version": np.uint16(334),
            "imageType": np.uint16(0),
            "label": np.bytes_(b"SE1"),
            "sMin": np.uint16(0),
            "sMax": np.uint16(0),
            "color": np.uint16(0),
            "presetMode": np.uint16(0),
            "presetTime": np.uint32(0),
            "dataType": np.uint16(0),
            "timeConstantOld": np.uint16(1),
            "reserved1": np.int16(0),
            "roiStartChan": np.uint16(0),
            "roiEndChan": np.uint16(0),
            "userMin": np.int16(0),
            "userMax": np.int16(0),
            "iADC": np.uint16(1),
            "reserved2": np.int16(0),
            "iBits": np.uint16(8),
            "nReads": np.uint16(23),
            "nFrames": np.uint16(1),
            "fDwell": np.float32(0.0),
            "accV": np.uint16(150),
            "tilt": np.int16(0),
            "takeoff": np.int16(35),
            "mag": np.uint32(211),
            "wd": np.uint16(1500),
            "mppX": np.float32(1.6013774),
            "mppY": np.float32(1.5876777),
            "nTextLines": np.uint16(0),
            "charText": [
                np.bytes_(b""),
                np.bytes_(b""),
                np.bytes_(b""),
                np.bytes_(b""),
            ],
            "reserved3": np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            "nOverlayElements": np.uint16(0),
            "overlayColors": np.array(
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.uint16
            ),
            "timeConstantNew": np.float32(6.0),
            "reserved4": np.array([0.0, 0.0], dtype=np.float32),
        }
    )
    orig_metadata["ipr_header"] = ipr_h  # type:ignore[assignment]
    spc_h = OrderedDict(
        {
            "filler1": np.void(b"bytesfiller"),
            "dataStart": np.int32(3840),
            "numPts": np.int16(4096),
            "filler1_1": np.void(b"bytesfiller"),
            "kV": np.float32(15.0),
            "filler6": np.void(b"bytesfiller"),
            "numElem": np.int16(8),
            "at": np.array(
                [
                    8,
                    11,
                    12,
                    13,
                    14,
                    19,
                    20,
                    26,
                    56014,
                    18951,
                    102,
                    0,
                    56900,
                    12409,
                    36648,
                    36109,
                    56928,
                    16495,
                    7152,
                    16496,
                    31816,
                    13680,
                    0,
                    197,
                    1,
                    0,
                    56720,
                    12409,
                    56832,
                    12409,
                    14464,
                    29986,
                    65535,
                    65535,
                    61930,
                    29923,
                    62063,
                    29923,
                    63956,
                    15924,
                    45704,
                    10930,
                    56812,
                    12409,
                    16461,
                    29903,
                    45704,
                    10930,
                ],
                dtype=np.uint16,
            ),
            "filler7": np.void(b"bytesfiller"),
        }
    )
    orig_metadata["spc_header"] = spc_h  # type:ignore[assignment]
    fake_raw_ds["original_metadata"] = orig_metadata  # type:ignore[assignment]

    return EDAX_raw_ds(fake_raw_ds)


class onDiscMock:
    filenames = (
        "faked-dataset-C12",
        "faked-dataset-2",
    )

    def __init__(self) -> None:
        pass

    def load(self, file: str) -> EDAX_raw_ds:
        if file in self.filenames:
            return createEDAXMock()
        msg = f"File {file} is not a fake file"
        raise ValueError(msg)


def pytest_running() -> bool:
    return os.environ.get("PYTEST_VERSION") is not None


_on_disc_mock = onDiscMock()

__all__ = ["_on_disc_mock", "createEDAXMock", "pytest_running"]

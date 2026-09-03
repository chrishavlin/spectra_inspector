import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

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


def createEDAXSpectrumMock(
    n_channels: int = 4096, ev_per_channel: int = 10, start_energy: float = 0.0
) -> EDAX_raw_ds:
    """A standalone ``.spc`` spectrum, shaped as rsciio's spc reader returns it.

    The defaults match a real EDAX export: 4096 channels of 10 eV, so the
    calibration windows (up to 15 keV) all fall inside the spectrum and the
    element weights can be computed.
    """
    rng = np.random.default_rng()
    intensity = (rng.random(n_channels) * 100).astype(np.uint32)

    # a spectrum's metadata comes out of the same header fields as a map's
    map_mock = createEDAXMock()
    metadata = map_mock.metadata
    metadata["General"] = {"original_filename": "C-12.spc", "title": "EDS Spectrum"}

    spc_h = OrderedDict(
        {
            "filler1": np.void(b"bytesfiller"),
            "dataStart": np.int32(20740),
            "numPts": np.int16(n_channels),
            "filler1_1": np.void(b"bytesfiller"),
            "evPerChan": np.int32(ev_per_channel),
            "filler2": np.void(b"bytesfiller"),
            "startEnergy": np.float32(start_energy),
            "endEnergy": np.float32(start_energy + n_channels * ev_per_channel / 1000),
            "liveTime": np.float32(3609.19),
            "tilt": np.float32(0.0),
            "filler3": np.void(b"bytesfiller"),
            "detReso": np.float32(125.65),
            "filler4": np.void(b"bytesfiller"),
            "azimuth": np.float32(0.0),
            "elevation": np.float32(33.5),
            "filler5": np.void(b"bytesfiller"),
            "kV": np.float32(15.0),
            "filler6": np.void(b"bytesfiller"),
            "numElem": np.int16(8),
            "at": np.array([8, 11, 12, 13, 14, 19, 20, 26] + [0] * 40, dtype=np.uint16),
            "filler7": np.void(b"bytesfiller"),
        }
    )

    return EDAX_raw_ds(
        {
            "data": intensity,
            "axes": [
                {
                    "size": n_channels,
                    "index_in_array": 0,
                    "name": "Energy",
                    "scale": ev_per_channel / 1000.0,
                    "offset": np.float32(start_energy),
                    "units": "keV",
                    "navigate": False,
                }
            ],
            "metadata": metadata,
            "original_metadata": {"spc_header": spc_h},
        }
    )


def write_mock_spc(
    path: Path,
    intensity: npt.NDArray[np.uint32] | None = None,
    ev_per_channel: int = 10,
    start_energy: float = 0.0,
    elements: tuple[int, ...] = (8, 11, 12, 13, 14, 19, 20, 26),
) -> npt.NDArray[np.uint32]:
    """Write a synthetic but genuine ``.spc`` file that rsciio can read.

    The header is laid out with rsciio's own dtype description of the parts of
    the header it reads, so the file round-trips through ``rsciio.edax`` like
    an EDAX export would. This is what lets the ``.spc`` loader be tested
    without checking a real spectrum into the repository.

    Returns the counts written, so a test can compare them to what is read.
    """
    from rsciio.edax._api import get_spc_dtype_list  # noqa: PLC0415

    if intensity is None:
        rng = np.random.default_rng(0)
        intensity = (rng.random(4096) * 100).astype(np.uint32)
    intensity = np.ascontiguousarray(intensity, dtype="<u4")

    header_dtype = np.dtype(
        get_spc_dtype_list(load_all=False, endianness="<")  # type: ignore[no-untyped-call]
    )
    # Any: numpy's stubs do not type field access on structured arrays
    header: Any = np.zeros(1, dtype=header_dtype)
    header["dataStart"] = header_dtype.itemsize
    header["numPts"] = len(intensity)
    header["evPerChan"] = ev_per_channel
    header["startEnergy"] = start_energy
    header["endEnergy"] = start_energy + len(intensity) * ev_per_channel / 1000
    header["liveTime"] = 3609.19
    header["detReso"] = 125.65
    header["elevation"] = 33.5
    header["kV"] = 15.0
    header["numElem"] = len(elements)
    at = np.zeros(48, dtype="<u2")
    at[: len(elements)] = elements
    header["at"] = at

    with Path(path).open("wb") as f:
        f.write(header.tobytes())
        f.write(intensity.tobytes())
    return intensity


class onDiscMock:
    """The synthetic samples accepted everywhere while pytest is running.

    ``filenames`` are maps; every map also has a ``.spc`` alongside it in a
    real export, so those names are valid spectra too, and ``spectrum_only``
    adds a spectrum with no map behind it.
    """

    filenames = (
        "faked-dataset-C12",
        "faked-dataset-2",
    )
    spectrum_only_filenames = ("faked-spectrum-only",)

    def __init__(self) -> None:
        pass

    @property
    def spectrum_filenames(self) -> tuple[str, ...]:
        return (*self.filenames, *self.spectrum_only_filenames)

    def is_mock(self, file: str, spectrum_only: bool = False) -> bool:
        if spectrum_only:
            return file in self.spectrum_filenames
        return file in self.filenames

    def load(self, file: str, spectrum_only: bool = False) -> EDAX_raw_ds:
        if not self.is_mock(file, spectrum_only=spectrum_only):
            msg = f"File {file} is not a fake file"
            raise ValueError(msg)
        if spectrum_only:
            return createEDAXSpectrumMock()
        return createEDAXMock()


def pytest_running() -> bool:
    return os.environ.get("PYTEST_VERSION") is not None


_on_disc_mock = onDiscMock()

__all__ = [
    "_on_disc_mock",
    "createEDAXMock",
    "createEDAXSpectrumMock",
    "pytest_running",
    "write_mock_spc",
]

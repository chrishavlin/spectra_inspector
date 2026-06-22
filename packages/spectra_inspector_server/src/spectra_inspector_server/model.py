from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel

from spectra_inspector_server.processor.utilities import _get_nested_dict_element


class EDAX_file_set(BaseModel):
    spd: Path
    spc: Path
    ipr: Path
    bmp: Path
    xml: Path


class EDAX_axis(BaseModel):
    size: int
    index_in_array: int
    name: str
    scale: float
    offset: int
    units: str
    navigate: bool


@dataclass
class Spectrum1dDict:
    energy: list[float]
    intensity: list[float]
    energy_min: float
    energy_max: float
    metadata: dict[str, Any] | None = None
    original_metadata: dict[str, Any] | None = None


@dataclass
class Spectrum1d:
    energy: npt.NDArray[np.int64]  # energy index
    intensity: npt.NDArray[np.int64]
    energy_min: float
    energy_max: float
    metadata: dict[str, Any] | None = None
    original_metadata: dict[str, Any] | None = None

    def tolist(self) -> list[list[float]]:
        return [self.energy.tolist(), self.intensity.tolist()]

    def todict(self) -> Spectrum1dDict:
        extra = {}
        if self.metadata:
            extra["metadata"] = self.metadata
        if self.original_metadata:
            extra["original_metadata"] = self.original_metadata

        return Spectrum1dDict(
            energy=self.energy.tolist(),
            intensity=self.intensity.tolist(),
            energy_min=self.energy_min,
            energy_max=self.energy_max,
            **extra,
        )


class GeneralMetadata(BaseModel):
    original_filename: str
    title: str


class Signal(BaseModel):
    signal_type: str


class EDS(BaseModel):
    azimuth_angle: float
    elevation_angle: float
    energy_resolution_MnKa: float
    live_time: float


class Detector(BaseModel):
    EDS: EDS


class Stage(BaseModel):
    tilt_alpha: float


class SEM(BaseModel):
    Detector: Detector
    beam_energy: float
    Stage: Stage


class AcquisitionInstrument(BaseModel):
    SEM: SEM


class Sample(BaseModel):
    elements: list[str]


class MetadataModel(BaseModel):
    General: GeneralMetadata
    Signal: Signal
    Acquisition_instrument: AcquisitionInstrument
    Sample: Sample


class CombinedMetadata(BaseModel):
    metadata: MetadataModel
    axes_by_index: dict[int, EDAX_axis]
    data_shape: tuple[int, int, int]


class EDAX_raw_ds:
    data: npt.NDArray[np.int64]
    axes: list[EDAX_axis]
    metadata: dict[str, Any]
    original_metadata: dict[str, Any]
    axes_by_index: dict[int, EDAX_axis]

    def __init__(self, raw_ds: dict[str, Any]):

        axes = [EDAX_axis(**ax_dict) for ax_dict in raw_ds["axes"]]

        valid_data: npt.NDArray[np.int64] = raw_ds["data"]
        self.data = valid_data
        self.axes = axes
        self.metadata = raw_ds["metadata"]
        self.original_metadata = raw_ds["original_metadata"]

        axes_by_index: dict[int, EDAX_axis] = {}
        for ax in axes:
            axes_by_index[ax.index_in_array] = ax
        self.axes_by_index = axes_by_index

    @property
    def refined_metadata(self) -> MetadataModel:
        md = self.metadata
        gm = GeneralMetadata(**md["General"])
        sig = Signal(**md["Signal"])

        eds = _get_nested_dict_element(
            md, ["Acquisition_instrument", "SEM", "Detector", "EDS"]
        )
        eds["azimuth_angle"] = float(eds["azimuth_angle"])
        eds["elevation_angle"] = float(eds["elevation_angle"])
        eds["energy_resolution_MnKa"] = float(eds["energy_resolution_MnKa"])
        eds["live_time"] = float(eds["live_time"])
        eds_inst = EDS(**eds)
        det = Detector(EDS=eds_inst)

        stage_dict = _get_nested_dict_element(
            md, ["Acquisition_instrument", "SEM", "Stage"]
        )
        stage_dict["tilt_alpha"] = float(stage_dict["tilt_alpha"])
        stage = Stage(**stage_dict)

        beam_energy = float(
            _get_nested_dict_element(
                md, ["Acquisition_instrument", "SEM", "beam_energy"]
            )
        )
        sem = SEM(Detector=det, Stage=stage, beam_energy=beam_energy)

        ai = AcquisitionInstrument(SEM=sem)

        samp = Sample(elements=md["Sample"]["elements"])

        return MetadataModel(
            General=gm,
            Signal=sig,
            Acquisition_instrument=ai,
            Sample=samp,
        )

    def _rescale_index(self, axis_id: int, index: int) -> float:
        axis = self.axes_by_index[axis_id]
        return float(axis.scale * index + axis.offset)

    def axis_range(
        self, axis_id: int, indx_start: int = 0, indx_end: int | None = None
    ) -> tuple[float, float]:
        """get physical range of an axis with optional subselection

        Parameters
        ----------
        axis_id : int
            the axis id index (0, 1 or 2)
        indx_start : int, optional
            starting index, by default 0
        indx_end : int | None, optional
            end index, by default None, will use max available index
            if None.

        Returns
        -------
        tuple[float, float]
            (min_val, max_val)

        """

        min_val = self._rescale_index(axis_id, indx_start)
        max_size = self.axes_by_index[axis_id].size
        if indx_end is None:
            indx_end = max_size
        assert isinstance(indx_end, int)

        if indx_end < indx_start:
            msg = f"end index is < start index: {indx_start=}, {indx_end=}"
            raise ValueError(msg)

        if indx_start < 0:
            msg = f"start index cannot be < 0: {indx_start=}"
            raise ValueError(msg)

        if indx_end > max_size:
            msg = f"end index cannot be > size of array: {indx_end=}, {max_size=}"
            raise ValueError(msg)

        max_val = self._rescale_index(axis_id, indx_end)
        return min_val, max_val


@dataclass
class Info:
    app_name: str
    spectra_inspector_data_root: str


@dataclass
class sampleMetadataCSVrecord:
    sample_id: str
    lat: float | None
    lon: float | None
    elevation: float | None
    group_name: str
    sample_type: str
    description: str

    @staticmethod
    def from_rec(rec: dict[str, str | float]) -> "sampleMetadataCSVrecord":

        sid = str(rec["sample_id"])
        sample_type = str(rec["sample_type"])
        group_name = str(rec["group_name"])
        description = str(rec["description"])

        elevation = None
        if rec["elevation"]:
            elevation = float(rec["elevation"])

        lat = None
        if rec["lat"]:
            lat = float(rec["lat"])

        lon = None
        if rec["lon"]:
            lon = float(rec["lon"])

        return sampleMetadataCSVrecord(
            sample_id=sid,
            lat=lat,
            lon=lon,
            sample_type=sample_type,
            group_name=group_name,
            description=description,
            elevation=elevation,
        )


@dataclass
class sampleMetadata:
    records: list[sampleMetadataCSVrecord] | None = None
    map_samples: dict[str, str] | None = None


@dataclass
class AvailableDatasets:
    available_files: list[str]
    sample_metadata: sampleMetadata | None = None


class raveledImage(BaseModel):
    image: list[int]
    shape: tuple[int, int]

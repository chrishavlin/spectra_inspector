# replace this with spectra_inspector_server imports when ready

from dataclasses import dataclass
from pydantic import BaseModel

@dataclass
class Spectrum1dDict:
    energy: list[float]
    intensity: list[float]
    energy_min: float
    energy_max: float


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


@dataclass
class Info:
    app_name: str
    spectra_inspector_data_root: str


@dataclass
class AvailableDatasets:
    available_files: list[str]

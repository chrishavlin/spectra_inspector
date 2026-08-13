from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel


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
    weights: dict[str, Any] | None = None


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


@dataclass
class Info:
    app_name: str
    spectra_inspector_data_root: str
    desktop_mode: bool = False


class directoryEntry(BaseModel):
    """a single subdirectory of a browsable directory."""

    name: str
    # posix-style path relative to the server's data root
    path: str


class directoryListing(BaseModel):
    """the browsable contents of one directory within the server's data root."""

    # posix-style path relative to the data root, "" for the data root itself
    path: str
    name: str
    # None when this listing is the data root: there is nowhere further up to go
    parent_path: str | None = None
    directories: list[directoryEntry] = []
    # number of EDAX file sets found directly in this directory
    dataset_count: int = 0


@dataclass
class sampleMetadataCSVrecord:
    sample_id: str
    lat: float
    lon: float
    elevation: float
    group_name: str
    sample_type: str
    description: str


@dataclass
class sampleMetadata:
    records: list[sampleMetadataCSVrecord] | None = None
    map_samples: dict[str, str] | None = None


@dataclass
class AvailableDatasets:
    available_files: list[str]
    sample_metadata: sampleMetadata | None = None
    # the directory the listing came from, relative to the server's data root.
    # None when the whole data root was scanned.
    directory: str | None = None


class raveledImage(BaseModel):
    image: list[int]
    shape: tuple[int, int]

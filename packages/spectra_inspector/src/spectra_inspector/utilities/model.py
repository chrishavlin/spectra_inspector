# DO NOT EDIT: generated from the spectra_inspector_server OpenAPI schema.
#
# Regenerate with:
#
#     cd packages/spectra_inspector_server
#     uv run --group codegen python ../../scripts/generate_frontend_models.py
#
# The server's model.py is the source of truth; edits made here are overwritten
# and the model-codegen CI job fails on any difference.

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EDAX_axis(BaseModel):
    size: int
    index_in_array: int
    name: str
    scale: float
    offset: float
    units: str
    navigate: bool


class EDS_1(BaseModel):
    azimuth_angle: float
    elevation_angle: float
    energy_resolution_MnKa: float
    live_time: float


class GeneralMetadata(BaseModel):
    original_filename: str
    title: str


class Info(BaseModel):
    app_name: str
    spectra_inspector_data_root: str
    desktop_mode: bool | None = False


class Sample_1(BaseModel):
    elements: list[str]


class Signal_1(BaseModel):
    signal_type: str


class Spectrum1dDict(BaseModel):
    energy: list[float]
    intensity: list[float]
    energy_min: float
    energy_max: float
    metadata: dict[str, Any] | None = None
    original_metadata: dict[str, Any] | None = None
    weights: dict[str, Any] | None = None


class Stage_1(BaseModel):
    tilt_alpha: float


class ValidationError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str
    input: Any | None = None
    ctx: dict[str, Any] | None = None


class directoryEntry(BaseModel):
    """
    a single subdirectory of a browsable directory.
    """

    name: str
    path: str


class directoryListing(BaseModel):
    """
    the browsable contents of one directory within the data root.
    """

    path: str
    name: str
    parent_path: str | None = None
    directories: list[directoryEntry] | None = Field([], validate_default=True)
    dataset_count: int | None = 0
    spectrum_count: int | None = 0


class raveledImage(BaseModel):
    image: list[int]
    shape: tuple[int, int]


class sampleMetadataCSVrecord(BaseModel):
    sample_id: str
    lat: float | None
    lon: float | None
    elevation: float | None
    group_name: str
    sample_type: str
    description: str


class Detector_1(BaseModel):
    EDS: EDS_1


class HTTPValidationError(BaseModel):
    detail: list[ValidationError] | None = None


class SEM_1(BaseModel):
    Detector: Detector_1
    beam_energy: float
    Stage: Stage_1


class sampleMetadata(BaseModel):
    records: list[sampleMetadataCSVrecord] | None = None
    map_samples: dict[str, str] | None = None


class AcquisitionInstrument(BaseModel):
    SEM: SEM_1


class AvailableDatasets(BaseModel):
    available_files: list[str]
    sample_metadata: sampleMetadata | None = None
    directory: str | None = None
    truncated: bool | None = False
    available_spectra: list[str] | None = None


class MetadataModel(BaseModel):
    General: GeneralMetadata
    Signal: Signal_1
    Acquisition_instrument: AcquisitionInstrument
    Sample: Sample_1


class CombinedMetadata(BaseModel):
    metadata: MetadataModel
    axes_by_index: dict[str, EDAX_axis]
    data_shape: list[int]


# These names collide with a field of the same name, so the generator
# suffixed the class. Alias them back to the spelling the server uses.
Detector = Detector_1
EDS = EDS_1
SEM = SEM_1
Sample = Sample_1
Signal = Signal_1
Stage = Stage_1

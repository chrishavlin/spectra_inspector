from typing import Literal

from spectra_inspector.server._file_tree_handling import EDAXPathHandler
from spectra_inspector.server._testing import pytest_running
from spectra_inspector.server.dependencies import get_database_session, get_settings
from spectra_inspector.server.model import (
    AvailableDatasets,
    CombinedMetadata,
    Info,
    MetadataModel,
    Spectrum1d,
    Spectrum1dDict,
    raveledImage,
)
from spectra_inspector.server.processor.operations import OperationEDAXStateHandler


def _valid_sample_name(sample_name: str, ph: EDAXPathHandler) -> bool:
    if sample_name in ph.database.available_maps:
        return True

    if pytest_running():
        from spectra_inspector.server._testing import _on_disc_mock

        return sample_name in _on_disc_mock.filenames

    return False


def info() -> Info:
    settings = get_settings()
    return Info(
        app_name=settings.app_name,
        spectra_inspector_data_root=settings.spectra_inspector_data_root,
    )


def available_datasets() -> AvailableDatasets:

    ph = get_database_session()
    filekeys = [str(nm) for nm in ph.database.available_maps]

    available_samples = ph.database.available_samples
    all_meta = ph.database.sample_metadata_mapper.get_all(
        available_samples=available_samples
    )
    return AvailableDatasets(available_files=filekeys, sample_metadata=all_meta)


def image_metadata(sample_name: str) -> MetadataModel:

    ph = get_database_session()
    _require_valid_sample_name(sample_name, ph)

    ops = OperationEDAXStateHandler(ph, allow_mock_files=pytest_running())
    return ops.get_refined_metadata(sample_name)


def _prep_operation(sample_name: str | None = None):
    ph = get_database_session()
    if sample_name:
        _require_valid_sample_name(sample_name, ph)
    return OperationEDAXStateHandler(ph, allow_mock_files=pytest_running())


def _require_valid_sample_name(sample_name: str, ph: EDAXPathHandler):
    if not _valid_sample_name(sample_name, ph):
        msg = f"{sample_name} is not a valid sample"
        raise RuntimeError(msg)


def image_metadata_combined(sample_name: str) -> CombinedMetadata:
    ops = _prep_operation(sample_name)
    return ops.get_combined_metadata(sample_name)


def _validate_range_kwarg(
    index_0: int | None | Literal["none"] = None,
    index_1: int | None | Literal["none"] = None,
):
    if isinstance(index_0, int) and isinstance(index_1, int):
        return int(index_0), int(index_1)
    return None


def image_spectrum(
    sample_name: str,
    channel_0: int | None = None,
    channel_1: int | None = None,
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
) -> Spectrum1dDict:

    ops = _prep_operation(sample_name)
    index0_range = _validate_range_kwarg(index0_0, index0_1)
    index1_range = _validate_range_kwarg(index1_0, index1_1)
    channel_range = _validate_range_kwarg(channel_0, channel_1)

    result = ops.get_spectrum(
        sample_name,
        channel_range=channel_range,
        index0_range=index0_range,
        index1_range=index1_range,
    )

    assert isinstance(result, Spectrum1d)
    return result.todict()  # type:ignore[unreachable]


def image_data(
    sample_name: str,
    channel_index: int,
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
) -> raveledImage:

    ops = _prep_operation(sample_name)
    index0_range = _validate_range_kwarg(index0_0, index0_1)
    index1_range = _validate_range_kwarg(index1_0, index1_1)

    result = ops.get_single_image(
        sample_name,
        channel_index=channel_index,
        index0_range=index0_range,
        index1_range=index1_range,
    )
    assert isinstance(result, raveledImage)
    return result


def image_data_summed(
    sample_name: str,
    channel_0: int,
    channel_1: int,
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
) -> raveledImage:

    ops = _prep_operation(sample_name)

    index0_range = _validate_range_kwarg(index0_0, index0_1)
    index1_range = _validate_range_kwarg(index1_0, index1_1)
    channel_range = _validate_range_kwarg(channel_0, channel_1)
    assert isinstance(channel_range, tuple)
    assert len(channel_range) == 2

    result = ops.get_raveled_multi_channel_intensity_image(
        sample_name,
        channel_range=channel_range,
        index0_range=index0_range,
        index1_range=index1_range,
    )
    assert isinstance(result, raveledImage)
    return result

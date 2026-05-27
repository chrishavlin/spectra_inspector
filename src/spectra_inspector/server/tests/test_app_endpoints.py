import numpy as np

from spectra_inspector.server import api as si_api
from spectra_inspector.server._testing import _on_disc_mock
from spectra_inspector.server.model import (
    MetadataModel,
)


def test_info():
    info = si_api.info()
    assert hasattr(info, "app_name")
    assert hasattr(info, "spectra_inspector_data_root")


def test_available_data():
    data = si_api.available_datasets()
    assert hasattr(data, "available_files")


def test_image_metadata() -> None:
    mm = si_api.image_metadata(_on_disc_mock.filenames[0])
    assert isinstance(mm, MetadataModel)
    assert mm.General.title == "EDS Spectrum Image"


def test_image_combined_metadata() -> None:
    mm = si_api.image_metadata_combined(_on_disc_mock.filenames[0])
    assert mm.metadata.General.title == "EDS Spectrum Image"
    assert len(mm.data_shape) == 3
    for indx in range(3):
        assert mm.axes_by_index[indx].size == mm.data_shape[indx]


def test_image_spectrum() -> None:
    spectrum = si_api.image_spectrum(_on_disc_mock.filenames[0])
    assert np.all(np.isreal(spectrum.energy))
    assert np.all(np.isreal(spectrum.intensity))


def test_image_data() -> None:
    spectrum = si_api.image_data(_on_disc_mock.filenames[0], channel_index=2)
    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))


def test_image_data_subset() -> None:
    spectrum = si_api.image_data(
        _on_disc_mock.filenames[0],
        channel_index=2,
        index0_0=2,
        index0_1=5,
        index1_0=3,
        index1_1=8,
    )
    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))

    assert spectrum.shape == (3, 5)


def test_image_data_summed() -> None:
    spectrum = si_api.image_data_summed(
        _on_disc_mock.filenames[0], channel_0=0, channel_1=4
    )
    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))


def test_image_data_summed_subset() -> None:

    spectrum = si_api.image_data_summed(
        _on_disc_mock.filenames[0],
        channel_0=0,
        channel_1=4,
        index0_0=2,
        index0_1=5,
        index1_0=3,
        index1_1=8,
    )

    assert len(spectrum.shape) == 2
    assert len(spectrum.image) == np.prod(spectrum.shape)
    assert np.all(np.isreal(spectrum.image))
    assert np.all(np.isreal(spectrum.shape))

    assert spectrum.shape == (3, 5)

import dataclasses

import numpy as np

from spectra_inspector_server.calibration import (
    calibration_elements,
    element_energy_ranges_keV,
)
from spectra_inspector_server.model import Spectrum1d, sampleMetadataCSVrecord


def test_spectrum1d() -> None:

    energy = np.arange(4).astype(float)
    s1d = Spectrum1d(
        energy=energy,
        intensity=np.linspace(0, 10, energy.size).astype(int),
        energy_min=0,
        energy_max=energy.max(),
    )

    s1d_dict = dataclasses.asdict(s1d.todict())
    assert "energy" in s1d_dict
    assert "intensity" in s1d_dict
    assert "energy_min" in s1d_dict
    assert "energy_max" in s1d_dict

    s1d.tolist()


def test_spectrum1d_weights_unavailable() -> None:
    # a spectrum that does not reach the 14-15 keV window cannot be weighted:
    # the weights come back as None instead of raising (issue #92).
    energy = np.arange(4).astype(float)
    s1d = Spectrum1d(
        energy=energy,
        intensity=np.linspace(0, 10, energy.size).astype(int),
        energy_min=0,
        energy_max=energy.max(),
    )

    assert s1d.get_weights() is None

    s1d_dict = dataclasses.asdict(s1d.todict(include_weights=True))
    assert s1d_dict["weights"] is None
    assert s1d_dict["integration_ranges_keV"] is None


def test_spectrum1d_weights_carry_their_integration_ranges() -> None:
    # 10 eV channels out to 40 keV span every calibration window, so the
    # weights come with the windows they were summed over (issue #120).
    energy = np.arange(4000).astype(float)
    s1d = Spectrum1d(
        energy=energy,
        intensity=np.ones(energy.size, dtype=int),
        energy_min=0.0,
        energy_max=40.0,
    )

    s1d_dict = dataclasses.asdict(s1d.todict(include_weights=True))
    assert s1d_dict["weights"] is not None
    ranges = s1d_dict["integration_ranges_keV"]
    assert set(ranges) == set(calibration_elements)
    assert ranges["Si"] == element_energy_ranges_keV["Si"]
    assert set(ranges) <= set(s1d_dict["weights"])

    assert dataclasses.asdict(s1d.todict())["integration_ranges_keV"] is None


def test_sampleMetadataCSVrecord() -> None:
    rec: dict[str, str | float] = {
        "sample_id": "test id",
        "lat": 45.0,
        "lon": -23.0,
        "elevation": 100,
        "group_name": "group name",
        "sample_type": "sample type",
        "description": "desc",
    }
    sampleMetadataCSVrecord.from_rec(rec)

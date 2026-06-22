import dataclasses

import numpy as np

from spectra_inspector_server.model import Spectrum1d, sampleMetadataCSVrecord


def test_spectrum1d() -> None:

    energy = np.arange(4)
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

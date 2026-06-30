from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from spectra_inspector.settings import Settings
from spectra_inspector.utilities import model as m
from spectra_inspector.utilities.summary_writer import summaryWriter


def test_summary_writer_cleanup(tmp_path):
    write_dir = tmp_path / "summary_dir"
    write_dir.mkdir()

    settings = Settings()
    settings.max_tmp_dirs = 2
    settings.write_dir = write_dir

    for _ in range(settings.max_tmp_dirs * 4):
        _ = summaryWriter(settings=settings)

    existing_dirs = [f for f in write_dir.glob("*") if f.is_dir()]
    assert len(existing_dirs) == settings.max_tmp_dirs + 1


@pytest.fixture
def writer(tmp_path):
    settings = Settings(
        write_dir=str(tmp_path),
        max_tmp_dirs=50,
    )
    return summaryWriter(
        cleanup_tmp_dirs=False,
        settings=settings,
    )


@pytest.fixture
def metadata():
    energy = np.array([0.0, 0.5, 1.0])
    intensity = np.array([10.0, 20.0, 30.0])

    metadata = m.MetadataModel(
        General=m.GeneralMetadata(
            original_filename="unittest.file", title="unit-tests"
        ),
        Signal=m.Signal(signal_type="EDS"),
        Acquisition_instrument=m.AcquisitionInstrument(
            SEM=m.SEM(
                beam_energy=15.0,
                Stage=m.Stage(tilt_alpha=0.0),
                Detector=m.Detector(
                    EDS=m.EDS(
                        azimuth_angle=0.0,
                        elevation_angle=33.5,
                        energy_resolution_MnKa=125.19505310058594,
                        live_time=9338.8798828125,
                    )
                ),
            )
        ),
        Sample=m.Sample(elements=[]),
    )

    return {
        "energy": energy,
        "intensity": intensity,
        "attrs": {
            "metadata": metadata.model_dump(),
            "original_metadata": {},
        },
    }


class TestWriteMSA:
    def test_write_msa_defaults_to_xy(self, writer, metadata):
        with patch("rsciio.msa.file_writer") as mock_writer:
            outfile = writer.write_MSA(
                metadata,
                file_type=".msa",
            )

        assert outfile.name == "spectrum.msa"

        mock_writer.assert_called_once()

        filename, signal = mock_writer.call_args.args
        assert filename == outfile

        assert signal["data"] is metadata["intensity"]

        axis = signal["axes"][0]
        assert axis["size"] == 3
        assert axis["index_in_array"] == 0
        assert axis["name"] == "Energy"
        assert axis["scale"] == pytest.approx(0.5)
        assert axis["offset"] == 0.0
        assert axis["units"] == "keV"
        assert axis["navigate"] is False

        assert signal["metadata"] == metadata["attrs"]["metadata"]
        assert signal["original_metadata"] == metadata["attrs"]["original_metadata"]

        assert mock_writer.call_args.kwargs["format"] == "XY"

    def test_write_msa_uses_requested_format(self, writer, metadata):
        with patch("rsciio.msa.file_writer") as mock_writer:
            writer.write_MSA(
                metadata,
                file_type=".msa",
                file_format="Y",
            )

        assert mock_writer.call_args.kwargs["format"] == "Y"

    def test_write_msa_builds_correct_axis(self, writer, metadata):
        with patch("rsciio.msa.file_writer") as mock_writer:
            writer.write_MSA(
                metadata,
                file_type=".msa",
            )

        signal = mock_writer.call_args.args[1]
        axis = signal["axes"][0]

        assert axis == {
            "size": 3,
            "index_in_array": 0,
            "name": "Energy",
            "scale": pytest.approx(0.5),
            "offset": 0.0,
            "units": "keV",
            "navigate": False,
        }

    def test_write_csv(self, writer, metadata):
        outfile = writer.write_MSA(
            metadata,
            file_type=".csv",
        )

        assert outfile.exists()
        assert outfile.name == "spectrum.csv"

        df = pd.read_csv(outfile)

        expected = pd.DataFrame(
            {
                "energy_keV": metadata["energy"],
                "intensity": metadata["intensity"],
            }
        )

        pd.testing.assert_frame_equal(df, expected)

    def test_write_csv_does_not_call_file_writer(self, writer, metadata):
        with patch("rsciio.msa.file_writer") as mock_writer:
            writer.write_MSA(
                metadata,
                file_type=".csv",
            )

        mock_writer.assert_not_called()

    def test_csv_and_msa_contain_same_spectral_data(self, writer, metadata):
        # Write both formats
        csv_file = writer.write_MSA(
            metadata,
            file_type=".csv",
        )

        msa_file = writer.write_MSA(
            metadata,
            file_type=".msa",
            file_format="XY",
        )

        # Read CSV
        csv_df = pd.read_csv(csv_file)

        # Read MSA data section
        energy = []
        intensity = []

        with open(msa_file) as f:
            in_spectrum = False

            for raw_line in f:
                line = raw_line.strip()

                if line.startswith("#SPECTRUM"):
                    in_spectrum = True
                    continue

                if line.startswith("#ENDOFDATA"):
                    break

                if not in_spectrum or not line:
                    continue

                e, i = line.split(",")
                energy.append(float(e.strip()))
                intensity.append(float(i.strip()))

        msa_df = pd.DataFrame(
            {
                "energy_keV": energy,
                "intensity": intensity,
            }
        )

        pd.testing.assert_frame_equal(csv_df, msa_df)

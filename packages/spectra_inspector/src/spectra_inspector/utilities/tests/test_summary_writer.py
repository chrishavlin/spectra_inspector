import json
import zipfile
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader

from spectra_inspector.components.data_export_panel import get_element_weights
from spectra_inspector.settings import Settings
from spectra_inspector.utilities import model as m
from spectra_inspector.utilities.matplotib_importer import mpl_pyplot as plt
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


def test_write_static_figures_writes_matplotlib_figure(writer):
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.imshow(np.arange(4).reshape(2, 2), cmap="viridis")

    writer.write_static_figures({"bitmap": fig}, figformat="png")

    out_file = writer.full_file("bitmap.png")
    assert out_file.exists()
    assert out_file.stat().st_size > 0


@pytest.fixture
def export_record() -> dict:
    return {
        "generated_utc": "2026-01-02T00:00:00+00:00",
        "dataset": "C-12",
        "spectrum_only": False,
        "sample": {
            "data_shape": [4, 4, 10],
            # outside latin-1: the PDF must replace it rather than fail
            "Sample Information": {"sample_id": "S1", "description": "岩石 5 µm"},
        },
        "subselection": {
            "shape": [2, 2],
            "axes": {
                "index0": {
                    "name": "y",
                    "index_range": [1, 3],
                    "bounds": [1.5, 4.5],
                    "units": "µm",
                },
                "index1": {
                    "name": "x",
                    "index_range": [0, 2],
                    "bounds": [0.0, 4.0],
                    "units": "µm",
                },
            },
        },
        "images": [],
        "spectrum": {"zeroed_elements": [], "peak_windows_shown": True},
    }


class TestMetadataExport:
    def test_metadata_files_require_a_record(self, writer):
        with pytest.raises(RuntimeError, match="set_export_metadata"):
            writer.write_metadata_files()

    def test_zip_carries_json_and_readme(self, writer, metadata, export_record):
        writer.write_MSA(metadata, file_type=".csv")
        writer.set_export_metadata(export_record)
        json_file, readme = writer.write_metadata_files()

        with zipfile.ZipFile(writer.get_zip()) as zf:
            names = set(zf.namelist())
        assert {"metadata.json", "README.txt", "spectrum.csv"} <= names

        assert json.loads(json_file.read_text(encoding="utf-8")) == export_record
        text = readme.read_text(encoding="utf-8")
        # every file in the zip is listed, this README included
        for name in names:
            assert name in text
        assert "index0 (y): indices [1, 3), 1.5 to 4.5 µm" in text
        assert "岩石 5 µm" in text

    def test_pdf_writes_the_metadata_pages(self, writer, export_record):
        fig = plt.figure()
        fig.add_subplot(111).plot([0, 1], [0, 1])
        writer.write_static_figures({"spectrum": fig})
        writer.set_export_metadata(export_record)

        pdf_path = writer.get_pdf_path()
        assert pdf_path.is_file()
        reader = PdfReader(pdf_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        assert "Sample metadata" in text
        assert "dataset: C-12" in text
        assert "sample_id: S1" in text
        assert "Box subselection" in text
        assert "1.5 to 4.5" in text

    def test_pdf_without_a_record(self, writer):
        fig = plt.figure()
        fig.add_subplot(111).plot([0, 1], [0, 1])
        writer.write_static_figures({"spectrum": fig})

        pdf_path = writer.get_pdf_path()
        text = "\n".join(page.extract_text() for page in PdfReader(pdf_path).pages)
        assert "not available for this export" in text


class TestElementWeightsExport:
    def test_zip_includes_element_weights(self, writer, metadata):
        metadata["attrs"]["weights"] = {"Na": 0.5, "total_count": 100.0}

        wts = get_element_weights(metadata)
        assert wts is not None
        writer.write_element_weights(wts)

        with zipfile.ZipFile(writer.get_zip()) as zf:
            names = zf.namelist()

        assert str(writer.element_weights_name) in names

    def test_zip_without_element_weights(self, writer, metadata):
        # the server sends a null weights for a spectrum it cannot calibrate
        # (issue #92): the export skips the weights file rather than failing.
        assert get_element_weights(metadata) is None

        writer.write_MSA(metadata, file_type=".csv")

        with zipfile.ZipFile(writer.get_zip()) as zf:
            names = zf.namelist()

        assert "spectrum.csv" in names
        assert str(writer.element_weights_name) not in names


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

import datetime

import pytest

from spectra_inspector.utilities import model as m
from spectra_inspector.utilities.export_metadata import (
    SAMPLE_INFORMATION_KEY,
    build_export_metadata,
    flatten_for_display,
    image_panel_metadata,
    readme_text,
    sample_metadata_display_dict,
    sample_record,
    subselection_lines,
    subselection_metadata,
)


def _axis(index: int, name: str, size: int, scale: float, offset: float = 0.0):
    return m.EDAX_axis(
        size=size,
        index_in_array=index,
        name=name,
        scale=scale,
        offset=offset,
        units="µm" if name != "Energy" else "keV",
        navigate=name != "Energy",
    )


@pytest.fixture
def combined_metadata() -> m.CombinedMetadata:
    metadata = m.MetadataModel(
        General=m.GeneralMetadata(original_filename="unittest.spd", title="unit"),
        Signal=m.Signal(signal_type="EDS"),
        Acquisition_instrument=m.AcquisitionInstrument(
            SEM=m.SEM(
                beam_energy=15.0,
                Stage=m.Stage(tilt_alpha=0.0),
                Detector=m.Detector(
                    EDS=m.EDS(
                        azimuth_angle=0.0,
                        elevation_angle=33.5,
                        energy_resolution_MnKa=125.0,
                        live_time=100.0,
                    )
                ),
            )
        ),
        Sample=m.Sample(elements=["Fe", "Si"]),
    )
    return m.CombinedMetadata(
        metadata=metadata,
        axes_by_index={
            "0": _axis(0, "y", 8, 1.5, offset=2.0),
            "1": _axis(1, "x", 6, 2.0),
            "2": _axis(2, "Energy", 10, 0.005),
        },
        data_shape=[8, 6, 10],
    )


@pytest.fixture
def sample_sheet() -> dict:
    record = {
        "sample_id": "S1",
        "lat": 40.0,
        "lon": -88.0,
        "elevation": 200.0,
        "group_name": "g",
        "sample_type": "rock",
        "description": "a rock",
    }
    return {"records": [record], "map_samples": {"C-12": "S1"}}


class TestSampleRecord:
    def test_finds_the_mapped_record(self, sample_sheet):
        assert sample_record(sample_sheet, "C-12")["sample_id"] == "S1"

    def test_missing_mapping_or_sheet(self, sample_sheet):
        assert sample_record(sample_sheet, "C-13") is None
        assert sample_record(None, "C-12") is None
        assert sample_record({}, "C-12") is None
        assert sample_record(sample_sheet, None) is None

    def test_mapping_without_record(self, sample_sheet):
        sample_sheet["records"] = []
        assert sample_record(sample_sheet, "C-12") is None


class TestDisplayDict:
    def test_matches_the_accordion(self, combined_metadata, sample_sheet):
        # the data-selection page shows exactly this: the combined metadata dump
        # plus the sample sheet record under "Sample Information"
        d = sample_metadata_display_dict(combined_metadata, sample_sheet, "C-12")
        expected = combined_metadata.model_dump()
        expected[SAMPLE_INFORMATION_KEY] = sample_sheet["records"][0]
        assert d == expected

    def test_without_a_record(self, combined_metadata):
        d = sample_metadata_display_dict(combined_metadata)
        assert d == combined_metadata.model_dump()
        assert SAMPLE_INFORMATION_KEY not in d


class TestSubselection:
    def test_bounds_follow_the_axes(self, combined_metadata):
        sub = subselection_metadata(combined_metadata, [1, 4], [2, 5])
        assert sub["shape"] == [3, 3]
        y = sub["axes"]["index0"]
        x = sub["axes"]["index1"]
        assert y["name"] == "y"
        assert y["index_range"] == [1, 4]
        assert y["bounds"] == pytest.approx([2.0 + 1.5, 2.0 + 4 * 1.5])
        assert y["units"] == "µm"
        assert x["name"] == "x"
        assert x["bounds"] == pytest.approx([4.0, 10.0])

    def test_lines(self, combined_metadata):
        sub = subselection_metadata(combined_metadata, [1, 4], [2, 5])
        lines = subselection_lines(sub)
        assert lines[0] == "Box shape (rows, columns): 3, 3"
        assert lines[1] == "index0 (y): indices [1, 4), 3.5 to 8 µm"
        assert lines[2] == "index1 (x): indices [2, 5), 4 to 10 µm"
        assert subselection_lines(None) == [
            "No box drawn: the images cover the full map."
        ]


def test_image_panel_metadata_names_the_files():
    panels = image_panel_metadata(
        [[0.0, 1.0], [6.275, 6.54]], ["none", "Fe"], ["viridis", "turbo"], True
    )
    assert [p["file"] for p in panels] == ["bitmap_00.png", "bitmap_01_Fe.png"]
    assert [p["subset_file"] for p in panels] == [
        "bitmap_00_subset.png",
        "bitmap_01_Fe_subset.png",
    ]
    assert panels[0]["element"] is None
    assert panels[1]["element"] == "Fe"
    assert panels[1]["energy_range_keV"] == [6.275, 6.54]
    assert panels[1]["colormap"] == "turbo"

    no_box = image_panel_metadata([[0.0, 1.0]], [None], ["viridis"], False)
    assert no_box[0]["subset_file"] is None


class TestBuildExportMetadata:
    def test_full_record(self, combined_metadata, sample_sheet):
        now = datetime.datetime(2026, 1, 2, tzinfo=datetime.UTC)
        images = image_panel_metadata([[0.0, 1.0]], ["Fe"], ["turbo"], True)
        record = build_export_metadata(
            "C-12",
            combined_metadata,
            sample_sheet,
            index_ranges=([1, 4], [2, 5]),
            images=images,
            zeroed_elements=["Si"],
            show_peak_windows=True,
            now=now,
        )
        assert record["generated_utc"] == "2026-01-02T00:00:00+00:00"
        assert record["dataset"] == "C-12"
        assert record["spectrum_only"] is False
        assert record["sample"][SAMPLE_INFORMATION_KEY]["sample_id"] == "S1"
        assert record["sample"]["data_shape"] == [8, 6, 10]
        assert record["subselection"]["shape"] == [3, 3]
        assert record["images"] == images
        assert record["spectrum"] == {
            "zeroed_elements": ["Si"],
            "peak_windows_shown": True,
        }

    def test_no_box(self, combined_metadata):
        record = build_export_metadata("C-12", combined_metadata)
        assert record["subselection"] is None
        assert record["images"] == []

    def test_spectrum_only_ignores_the_box(self, combined_metadata):
        record = build_export_metadata(
            "C-12", combined_metadata, spectrum_only=True, index_ranges=([0, 1], [0, 1])
        )
        assert record["spectrum_only"] is True
        assert record["subselection"] is None

    def test_without_server_metadata(self, sample_sheet):
        record = build_export_metadata(
            "C-12", None, sample_sheet, index_ranges=([0, 1], [0, 1])
        )
        assert record["sample"] is None
        assert record["subselection"] is None


def test_flatten_for_display_indents_nested_dicts():
    lines = flatten_for_display({"a": 1, "b": {"c": 2.5, "d": [1, 2]}, "e": "x"})
    assert lines == ["a: 1", "b:", "  c: 2.5", "  d: 1, 2", "e: x"]


def test_readme_describes_every_file(combined_metadata, sample_sheet):
    images = image_panel_metadata([[6.275, 6.54]], ["Fe"], ["turbo"], True)
    record = build_export_metadata(
        "C-12",
        combined_metadata,
        sample_sheet,
        index_ranges=([1, 4], [2, 5]),
        images=images,
    )
    files = [
        "bitmap_00_Fe.png",
        "bitmap_00_Fe_subset.png",
        "spectrum.png",
        "spectrum.msa",
        "spectrum.csv",
        "ElementWeights.txt",
        "metadata.json",
        "README.txt",
        "other.dat",
    ]
    text = readme_text(record, files)
    assert "Dataset: C-12" in text
    assert (
        "bitmap_00_Fe.png: map of the Fe window, 6.275, 6.54 keV, colormap turbo"
        in text
    )
    assert "bitmap_00_Fe_subset.png: the box region of bitmap_00_Fe.png" in text
    assert "metadata.json: this record as JSON" in text
    assert "\nother.dat\n" in text
    assert "index0 (y): indices [1, 4), 3.5 to 8 µm" in text
    assert "Zeroed-out elements: none" in text
    assert "  sample_id: S1" in text
    assert "original_filename: unittest.spd" in text


def test_readme_without_server_metadata():
    text = readme_text(build_export_metadata("C-12", None), ["spectrum.png"])
    assert "unavailable: the server could not be reached for it" in text
    assert "No box drawn" in text

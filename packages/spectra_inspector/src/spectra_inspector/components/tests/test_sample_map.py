import pytest

from spectra_inspector.components import sample_map
from spectra_inspector.components.sample_map import RING_TRACE, SAMPLE_TRACE
from spectra_inspector.utilities.model import (
    AvailableDatasets,
    sampleMetadata,
    sampleMetadataCSVrecord,
)

RECORDS = [
    {"sample_id": "C-12", "lat": -50.9, "lon": -72.9},
    {"sample_id": "C-29", "lat": -51.0, "lon": -73.0},
    {"sample_id": "C-36", "lat": None, "lon": None},
]


def _available(records: list[dict]) -> AvailableDatasets:
    return AvailableDatasets(
        available_files=[],
        sample_metadata=sampleMetadata(
            records=[
                sampleMetadataCSVrecord(
                    elevation=None,
                    group_name="g",
                    sample_type="t",
                    description="d",
                    **record,
                )
                for record in records
            ]
        ),
    )


def _point(sample_id, curve=SAMPLE_TRACE) -> dict:
    return {"curveNumber": curve, "customdata": ["granite", 12.0, sample_id]}


def test_sample_ids_from_points_reads_last_customdata_column():
    assert sample_map.sample_ids_from_points({"points": [_point("C-29")]}) == ["C-29"]


def test_sample_ids_from_points_scalar_customdata():
    click = {"points": [{"customdata": "C-29"}]}
    assert sample_map.sample_ids_from_points(click) == ["C-29"]


def test_sample_ids_from_points_keeps_order_without_repeats():
    selected = {"points": [_point("C-29"), _point("C-12"), _point("C-29")]}
    assert sample_map.sample_ids_from_points(selected) == ["C-29", "C-12"]


def test_sample_ids_from_points_skips_the_active_marker():
    selected = {"points": [_point("C-29", curve=RING_TRACE), _point("C-12")]}
    assert sample_map.sample_ids_from_points(selected) == ["C-12"]


@pytest.mark.parametrize(
    "event", [None, {}, {"points": []}, {"points": [{"lat": 1.0, "lon": 2.0}]}]
)
def test_sample_ids_from_points_handles_missing(event):
    assert sample_map.sample_ids_from_points(event) == []


def test_point_styling_without_a_filter_dims_nothing():
    styling = sample_map.point_styling(RECORDS)
    assert styling == {
        "selectedpoints": None,
        "ring": {"lat": [], "lon": []},
        "center": None,
    }


def test_point_styling_with_every_sample_visible_dims_nothing():
    styling = sample_map.point_styling(RECORDS, {"C-12", "C-29", "C-36", "other"})
    assert styling["selectedpoints"] is None


def test_point_styling_selects_the_visible_samples():
    assert sample_map.point_styling(RECORDS, {"C-29"})["selectedpoints"] == [1]
    assert sample_map.point_styling(RECORDS, set())["selectedpoints"] == []


def test_point_styling_marks_and_centers_the_active_sample():
    styling = sample_map.point_styling(RECORDS, None, "C-29")
    assert styling["ring"] == {"lat": [-51.0], "lon": [-73.0]}
    assert styling["center"] == {"lat": -51.0, "lon": -73.0}


@pytest.mark.parametrize("active", ["C-36", "unknown"])
def test_point_styling_without_a_location_for_the_active_sample(active):
    styling = sample_map.point_styling(RECORDS, None, active)
    assert styling["ring"] == {"lat": [], "lon": []}
    assert styling["center"] is None


def test_get_map_puts_the_active_marker_under_the_samples():
    fig = sample_map.get_map("satellite", _available(RECORDS[:2]))
    assert len(fig.data) == 2
    assert list(fig.data[RING_TRACE].lat) == []
    assert [row[-1] for row in fig.data[SAMPLE_TRACE].customdata] == ["C-12", "C-29"]
    assert fig.layout.showlegend is False


def test_get_map_revision_follows_the_samples():
    one = sample_map.get_map("satellite", _available(RECORDS[:2]))
    same = sample_map.get_map("open-street-map", _available(RECORDS[:2]))
    other = sample_map.get_map("satellite", _available(RECORDS[:1]))
    assert one.layout.uirevision == same.layout.uirevision
    assert one.layout.uirevision != other.layout.uirevision


@pytest.mark.parametrize("available", [None, _available([])])
def test_get_map_without_samples_shows_the_placeholder(available):
    fig = sample_map.get_map("satellite", available)
    assert len(fig.data[SAMPLE_TRACE].lat) == 1


def test_apply_point_styling_to_a_figure():
    fig = sample_map.get_map("satellite", _available(RECORDS[:2]))
    styling = sample_map.point_styling(RECORDS[:2], {"C-29"}, "C-29")
    sample_map.apply_point_styling(fig, styling)
    assert fig.data[SAMPLE_TRACE].selectedpoints == (1,)
    assert list(fig.data[RING_TRACE].lat) == [-51.0]
    assert fig.layout.map.center.lat == -51.0


def test_apply_point_styling_without_an_active_sample_keeps_the_center():
    fig = sample_map.get_map("satellite", _available(RECORDS[:2]))
    center = fig.layout.map.center.lat
    sample_map.apply_point_styling(fig, sample_map.point_styling(RECORDS[:2]))
    assert fig.layout.map.center.lat == center
    assert fig.data[SAMPLE_TRACE].selectedpoints is None

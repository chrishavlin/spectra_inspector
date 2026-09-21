import plotly.graph_objects as go
import pytest

from spectra_inspector.utilities.selection import (
    DEFAULT_VERTEX_RADIUS,
    END_VERTEX_COLOR,
    MIN_POLYGON_POINTS,
    POLYGON_COLOR,
    START_VERTEX_COLOR,
    active_shapes,
    add_point,
    box_from_shape,
    boxSelection,
    insert_point_on_nearest_segment,
    move_point,
    nearest_point,
    nearest_segment,
    pick_tolerance,
    polygon_is_submittable,
    polygon_points,
    polygon_shapes,
    polygon_store,
    polygonSelection,
    remove_nearest_point,
    selection_from_store,
    selection_key,
    submitted_polygon,
    vertex_radius,
    vertex_radius_for,
)

TRIANGLE = [[2.0, 1.0], [8.0, 1.0], [5.0, 6.0]]
RECT = {"type": "rect", "x0": 0.2, "x1": 3.7, "y0": 5.9, "y1": 1.1}


def test_box_from_shape_floors_and_sorts():
    box = box_from_shape(RECT)
    assert box == boxSelection(index0_range=(1, 5), index1_range=(0, 3))
    assert box.request_kwargs() == {"index0_range": (1, 5), "index1_range": (0, 3)}
    assert box.bounding_box((100, 100)) == ((1, 5), (0, 3))
    with pytest.raises(TypeError, match="Unsupported"):
        box_from_shape({"type": "circle"})


def test_polygon_vertices_are_row_column_for_the_server():
    poly = polygonSelection(((2.0, 1.0), (8.0, 1.5), (5.0, 6.0)))
    assert poly.vertices == [[1.0, 2.0], [1.5, 8.0], [6.0, 5.0]]
    assert poly.request_kwargs() == {"polygon": poly.vertices}


def test_polygon_bounding_box_covers_reachable_pixel_centres():
    poly = polygonSelection(((2.5, 1.0), (8.0, 1.5), (5.0, 6.2)))
    # rows: ceil(1.0)=1 .. floor(6.2)=6 -> [1, 7); columns: ceil(2.5)=3 .. 8 -> [3, 9)
    assert poly.bounding_box() == ((1, 7), (3, 9))
    assert poly.bounding_box((5, 5)) == ((1, 5), (3, 5))
    off_image = polygonSelection(((20.0, 20.0), (30.0, 20.0), (25.0, 30.0)))
    assert off_image.bounding_box((10, 10)) == ((10, 10), (10, 10))


class TestStore:
    def test_empty(self):
        for store in (None, {}, {"active_shapes": []}):
            assert selection_from_store(store) is None
            assert polygon_points(store) == []
            assert submitted_polygon(store) is None
            assert not polygon_is_submittable(store)
            assert selection_key(store) == "full"

    def test_box(self):
        store = {"active_shapes": [RECT]}
        assert selection_from_store(store) == box_from_shape(RECT)
        assert selection_key(store) != "full"

    def test_polygon_in_progress_is_not_a_selection(self):
        store = polygon_store(TRIANGLE, None)
        assert polygon_points(store) == TRIANGLE
        assert submitted_polygon(store) is None
        assert selection_from_store(store) is None
        assert selection_key(store) == "full"
        assert polygon_is_submittable(store)
        assert active_shapes(store) == polygon_shapes(TRIANGLE)

    def test_submitted_polygon_is_the_selection(self):
        store = polygon_store(TRIANGLE, TRIANGLE)
        selection = selection_from_store(store)
        assert isinstance(selection, polygonSelection)
        assert selection.points == tuple(tuple(p) for p in TRIANGLE)
        assert not polygon_is_submittable(store)
        # a further point is drawn but the submitted polygon stays selected
        edited = polygon_store(add_point(TRIANGLE, 4.0, 4.0), TRIANGLE)
        assert selection_from_store(edited) == selection
        assert polygon_is_submittable(edited)
        assert selection_key(edited) == selection_key(store)

    def test_too_few_points_cannot_be_submitted(self):
        store = polygon_store(TRIANGLE[:2], None)
        assert not polygon_is_submittable(store)
        assert MIN_POLYGON_POINTS == 3

    def test_keys_tell_selections_apart(self):
        keys = {
            selection_key({"active_shapes": [RECT]}),
            selection_key(polygon_store(TRIANGLE, TRIANGLE)),
            selection_key(polygon_store(TRIANGLE[::-1], TRIANGLE[::-1])),
            selection_key(None),
        }
        assert len(keys) == 4


class TestShapes:
    def test_one_point_is_a_marker_only(self):
        shapes = polygon_shapes(TRIANGLE[:1], radius=0.5)
        assert [s["type"] for s in shapes] == ["circle"]
        marker = shapes[0]
        assert (marker["x0"], marker["x1"]) == (1.5, 2.5)
        assert (marker["y0"], marker["y1"]) == (0.5, 1.5)
        assert marker["editable"] is False
        # never pixel-sized: a box drawn afterwards would inherit that mode
        assert "xsizemode" not in marker

    def test_marker_radius_follows_the_visible_extent(self):
        assert vertex_radius_for((100.0, 50.0)) == pytest.approx(0.8)
        assert vertex_radius(None) == DEFAULT_VERTEX_RADIUS
        store = polygon_store(TRIANGLE, None, radius=0.25)
        assert vertex_radius(store) == 0.25
        assert active_shapes(store)[-1]["x1"] - active_shapes(store)[-1]["x0"] == 0.5

    def test_two_points_are_an_open_line(self):
        shapes = polygon_shapes(TRIANGLE[:2])
        assert [s["type"] for s in shapes] == ["path", "circle", "circle"]
        assert shapes[0]["path"] == "M 2.0,1.0 L 8.0,1.0"
        assert shapes[0]["editable"] is False

    def test_three_points_close(self):
        shapes = polygon_shapes(TRIANGLE)
        assert shapes[0]["path"] == "M 2.0,1.0 L 8.0,1.0 L 5.0,6.0 Z"
        assert shapes[0]["fillcolor"] != "rgba(0,0,0,0)"
        assert len(shapes) == 4

    def test_start_and_end_corners_are_coloured(self):
        colours = [
            s["fillcolor"] for s in polygon_shapes(TRIANGLE) if s["type"] == "circle"
        ]
        assert colours == [START_VERTEX_COLOR, POLYGON_COLOR, END_VERTEX_COLOR]
        two = [
            s["fillcolor"]
            for s in polygon_shapes(TRIANGLE[:2])
            if s["type"] == "circle"
        ]
        assert two == [START_VERTEX_COLOR, END_VERTEX_COLOR]
        # a lone corner is where the path starts
        (only,) = polygon_shapes(TRIANGLE[:1])
        assert only["fillcolor"] == START_VERTEX_COLOR
        assert START_VERTEX_COLOR != END_VERTEX_COLOR != POLYGON_COLOR

    def test_shapes_are_valid_plotly(self):
        fig = go.Figure()
        fig.update_layout(shapes=polygon_shapes(TRIANGLE))
        assert len(fig.layout.shapes) == 4


class TestPoints:
    def test_add(self):
        assert add_point([], 1, 2) == [[1.0, 2.0]]
        assert add_point(TRIANGLE, 0, 0) == [*TRIANGLE, [0.0, 0.0]]

    def test_add_on_an_existing_corner_is_a_no_op(self):
        assert add_point(TRIANGLE, 8.1, 1.0, tolerance=0.5) == TRIANGLE
        assert add_point(TRIANGLE, 8.1, 1.0, tolerance=0.05) == [*TRIANGLE, [8.1, 1.0]]
        assert add_point([], 8.1, 1.0, tolerance=0.5) == [[8.1, 1.0]]

    def test_move(self):
        assert move_point(TRIANGLE, 1, 9.0, 2.0) == [
            TRIANGLE[0],
            [9.0, 2.0],
            TRIANGLE[2],
        ]
        assert move_point(TRIANGLE, 3, 9.0, 2.0) == TRIANGLE
        assert move_point(TRIANGLE, -1, 9.0, 2.0) == TRIANGLE
        assert move_point([], 0, 1.0, 1.0) == []

    def test_nearest_segment_of_a_closed_polygon(self):
        # the three segments of TRIANGLE: 0-1 along y=1, 1-2 and 2-0 (closing)
        assert nearest_segment(TRIANGLE, 5.0, 0.5) == (0, pytest.approx(0.5))
        index, distance = nearest_segment(TRIANGLE, 3.0, 4.0)
        assert index == 2  # the closing segment from (5, 6) back to (2, 1)
        assert distance < 1.0
        # beyond a segment's end the distance is to the corner
        assert nearest_segment(TRIANGLE, 9.0, 1.0) == (0, pytest.approx(1.0))

    def test_nearest_segment_of_an_open_path(self):
        two = TRIANGLE[:2]
        assert nearest_segment(two, 5.0, 2.0) == (0, pytest.approx(1.0))
        assert nearest_segment(TRIANGLE[:1], 0, 0) is None
        assert nearest_segment([], 0, 0) is None

    def test_insert_on_the_nearest_segment(self):
        inserted = insert_point_on_nearest_segment(TRIANGLE, 5.0, 0.8, tolerance=0.5)
        assert inserted == [TRIANGLE[0], [5.0, 0.8], TRIANGLE[1], TRIANGLE[2]]
        # on the closing segment the corner goes after the last one
        closing = insert_point_on_nearest_segment(TRIANGLE, 3.4, 3.5, tolerance=1.0)
        assert closing == [*TRIANGLE, [3.4, 3.5]]
        assert insert_point_on_nearest_segment(TRIANGLE, 5.0, 0.8, tolerance=0.1) == (
            TRIANGLE
        )
        assert insert_point_on_nearest_segment([], 0, 0, tolerance=5) == []

    def test_nearest(self):
        assert nearest_point([], 0, 0) is None
        index, distance = nearest_point(TRIANGLE, 7.0, 1.0)
        assert index == 1
        assert distance == pytest.approx(1.0)

    def test_remove_within_tolerance(self):
        assert remove_nearest_point(TRIANGLE, 7.5, 1.2, tolerance=1.0) == [
            TRIANGLE[0],
            TRIANGLE[2],
        ]
        # too far from every corner: nothing changes
        assert remove_nearest_point(TRIANGLE, 7.5, 1.2, tolerance=0.1) == TRIANGLE
        assert remove_nearest_point([], 0, 0, tolerance=5) == []

    def test_tolerance_tracks_the_visible_extent(self):
        assert pick_tolerance((100.0, 50.0)) == pytest.approx(4.0)
        assert pick_tolerance((10.0, 50.0)) == pytest.approx(2.0)
        assert pick_tolerance((100.0, 100.0), fraction=0.1) == pytest.approx(10.0)

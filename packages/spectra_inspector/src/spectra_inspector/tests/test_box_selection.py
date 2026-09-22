"""A box dragged out past the image: the request is clipped to the map (the
server rejects index ranges past it) while the rectangle stays as drawn, and
a box with no pixel inside the map is never stored, synced or shown."""

import importlib

import pytest

from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.tests.test_export_summary import combined_metadata
from spectra_inspector.user_store_model import UserStore
from spectra_inspector.utilities.selection import (
    box_from_shape,
    box_misses_image,
    boxSelection,
    polygon_store,
    polygonSelection,
    selection_from_store,
)

SHAPE = (4, 6)


def _rect(x0: float, x1: float, y0: float, y1: float) -> dict:
    return {"type": "rect", "x0": x0, "x1": x1, "y0": y0, "y1": y1}


@pytest.fixture
def inspector(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    import dash

    from spectra_inspector.main import app  # noqa: F401

    return importlib.import_module(dash.page_registry["pages.inspector"]["module"])


def test_box_from_shape_is_the_rectangle_as_drawn_without_a_shape():
    box = box_from_shape(_rect(-3.2, 8.0, 2.5, -1.0))
    assert box == boxSelection((-1, 2), (-4, 8))
    assert not box.is_empty


def test_box_from_shape_clips_to_the_image():
    box = box_from_shape(_rect(-3.2, 8.0, 2.5, -1.0), SHAPE)
    assert box == boxSelection((0, 2), (0, 6))
    assert box.request_kwargs() == {"index0_range": (0, 2), "index1_range": (0, 6)}
    assert box.bounding_box(SHAPE) == ((0, 2), (0, 6))


@pytest.mark.parametrize(
    "shape",
    [
        _rect(7.0, 9.0, 0.0, 2.0),  # right of the image
        _rect(-5.0, -1.0, 0.0, 2.0),  # left of it
        _rect(0.0, 2.0, 5.0, 8.0),  # below it
        _rect(0.0, 2.0, -3.0, -1.0),  # above it
        _rect(9.0, 12.0, 9.0, 12.0),  # off both axes
    ],
)
def test_a_box_with_no_pixel_inside_is_empty(shape: dict):
    assert box_from_shape(shape, SHAPE).is_empty
    assert box_misses_image([shape], SHAPE)


def test_a_box_over_the_edge_still_covers_something():
    shape = _rect(4.0, 9.0, 2.0, 8.0)
    assert not box_from_shape(shape, SHAPE).is_empty
    assert not box_misses_image([shape], SHAPE)
    assert not box_misses_image([], SHAPE)
    assert not box_misses_image(
        polygon_store([[0, 0], [9, 0], [9, 9]], None)["active_shapes"], SHAPE
    )


def test_selection_from_store_clips_the_box_when_it_knows_the_image():
    store = {"active_shapes": [_rect(4.0, 9.0, 2.0, 8.0)]}
    assert selection_from_store(store) == boxSelection((2, 8), (4, 9))
    assert selection_from_store(store, SHAPE) == boxSelection((2, 4), (4, 6))


def test_a_box_dragged_off_the_map_is_not_stored(inspector):
    md = combined_metadata(SHAPE)
    current = [_rect(0.0, 2.0, 0.0, 2.0)]
    store = {"active_shapes": current}

    # drawn wholly outside: the panels go back to the stored box, the store
    # is left alone
    relay = {"shapes": [*current, _rect(7.0, 9.0, 0.0, 2.0)]}
    shapes, redraw, keep = inspector._shapes_after_relayout(relay, store, lambda: md)
    assert (shapes, redraw, keep) == (current, True, False)

    # the stored box dragged off the map: same
    relay = {"shapes[0].x0": 7.0, "shapes[0].x1": 9.0}
    shapes, redraw, keep = inspector._shapes_after_relayout(relay, store, lambda: md)
    assert (shapes, redraw, keep) == (current, True, False)

    # hanging over the edge: stored as drawn, not clipped
    over = _rect(4.0, 9.0, 2.0, 8.0)
    relay = {"shapes": [*current, over]}
    shapes, redraw, keep = inspector._shapes_after_relayout(relay, store, lambda: md)
    assert (shapes, redraw, keep) == ([over], True, True)

    # nothing about shapes in the event
    _, redraw, keep = inspector._shapes_after_relayout(
        {"xaxis.range[0]": 1.0}, store, lambda: md
    )
    assert (redraw, keep) == (False, False)


def test_polygon_and_view_events_never_fetch_metadata(inspector):
    def explode():
        msg = "no metadata needed"
        raise AssertionError(msg)

    polygon = polygon_store([[0, 0], [9, 0], [9, 9]], None)
    relay = {"shapes": polygon["active_shapes"]}
    _, redraw, keep = inspector._shapes_after_relayout(relay, None, explode)
    assert (redraw, keep) == (True, True)
    assert inspector._selection_for_request(polygon, {}, "sample") is None


def test_selection_for_request_clips_the_box_to_the_map(inspector, monkeypatch):
    monkeypatch.setattr(
        UserStore,
        "conditionally_fetch_metadata",
        lambda _self: combined_metadata(SHAPE),
    )
    store = {"active_shapes": [_rect(4.0, 9.0, 2.0, 8.0)]}
    assert inspector._selection_for_request(store, {}, "sample") == boxSelection(
        (2, 4), (4, 6)
    )
    submitted = polygon_store([[0, 0], [9, 0], [9, 9]], [[0, 0], [9, 0], [9, 9]])
    selection = inspector._selection_for_request(submitted, {}, "sample")
    assert isinstance(selection, polygonSelection)
    assert selection.vertices == [[0.0, 0.0], [0.0, 9.0], [9.0, 9.0]]

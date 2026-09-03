"""The shared image view is rebuilt from relayoutData events (issue #65).

These pin down how the flattened keys plotly emits for a zoom, a pan, a
double-click reset, a tool change and a box annotation fold into the view, and
how that view is put back onto a figure.
"""

import plotly.express as px
import pytest
from dash import Patch

from spectra_inspector.utilities.view_sync import (
    DEFAULT_AUTORANGE,
    apply_axes_to_patch,
    apply_view_to_figure,
    empty_view,
    ensure_view,
    shapes_from_relayout,
    sorted_axis_range,
    update_view_from_relayout,
)

ZOOM = {
    "xaxis.range[0]": 153.06,
    "xaxis.range[1]": 306.71,
    "yaxis.range[0]": 297.77,
    "yaxis.range[1]": 138.02,
}
RESET = {"xaxis.autorange": True, "yaxis.autorange": True}


def _ops(patch: Patch) -> dict[str, object]:
    """{location path: value} for the operations recorded on a Patch."""
    result = {}
    for op in patch.to_plotly_json()["operations"]:
        loc = ".".join(str(p) for p in op["location"])
        result[loc] = op["params"].get("value", op["operation"])
    return result


def test_ensure_view_fills_in_and_drops_unknown_keys():
    assert ensure_view(None) == empty_view()
    assert ensure_view({}) == empty_view()
    view = ensure_view({"dragmode": "pan", "stale": 1})
    assert view == {"dragmode": "pan", "xaxis": None, "yaxis": None}


def test_zoom_sets_both_axes_in_plotly_order():
    view, axes_changed, dragmode_changed = update_view_from_relayout(empty_view(), ZOOM)
    assert axes_changed
    assert not dragmode_changed
    assert view["xaxis"] == {"range": [153.06, 306.71]}
    # the reversed y axis stays reversed
    assert view["yaxis"] == {"range": [297.77, 138.02]}
    assert sorted_axis_range(view, "yaxis") == [138.02, 297.77]


def test_double_click_resets_to_default_view():
    zoomed, _, _ = update_view_from_relayout(empty_view(), ZOOM)
    view, axes_changed, _ = update_view_from_relayout(zoomed, RESET)
    assert axes_changed
    assert view["xaxis"] is None
    assert view["yaxis"] is None
    assert sorted_axis_range(view, "xaxis") is None


def test_explicit_range_list_is_accepted():
    # what plotly emits for an axis that had an initial range
    relay = {"xaxis.autorange": True, "yaxis.range": [511.5, -0.5]}
    view, axes_changed, _ = update_view_from_relayout(empty_view(), relay)
    assert axes_changed
    assert view["xaxis"] is None
    assert view["yaxis"] == {"range": [511.5, -0.5]}


def test_single_axis_zoom_leaves_the_other_alone():
    zoomed, _, _ = update_view_from_relayout(empty_view(), ZOOM)
    view, axes_changed, _ = update_view_from_relayout(
        zoomed, {"xaxis.range[0]": 0.0, "xaxis.range[1]": 10.0}
    )
    assert axes_changed
    assert view["xaxis"] == {"range": [0.0, 10.0]}
    assert view["yaxis"] == zoomed["yaxis"]


def test_one_end_of_a_range_updates_in_place():
    zoomed, _, _ = update_view_from_relayout(empty_view(), ZOOM)
    view, axes_changed, _ = update_view_from_relayout(zoomed, {"xaxis.range[1]": 200.0})
    assert axes_changed
    assert view["xaxis"] == {"range": [153.06, 200.0]}


def test_dragmode_only_flags_dragmode():
    view, axes_changed, dragmode_changed = update_view_from_relayout(
        empty_view(), {"dragmode": "zoom"}
    )
    assert dragmode_changed
    assert not axes_changed
    assert view["dragmode"] == "zoom"
    # the same tool again is not a change
    _, _, dragmode_changed = update_view_from_relayout(view, {"dragmode": "zoom"})
    assert not dragmode_changed


@pytest.mark.parametrize("relay", [{}, {"autosize": True}, {"shapes": []}])
def test_irrelevant_events_change_nothing(relay):
    view, axes_changed, dragmode_changed = update_view_from_relayout(
        empty_view(), relay
    )
    assert view == empty_view()
    assert not axes_changed
    assert not dragmode_changed


def test_drawing_keeps_only_the_latest_shape():
    first = {"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}
    second = {"type": "rect", "x0": 5, "x1": 6, "y0": 5, "y1": 6}
    shapes, changed = shapes_from_relayout({"shapes": [first, second]}, [first])
    assert changed
    assert shapes == [second]


def test_erasing_clears_shapes():
    first = {"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}
    shapes, changed = shapes_from_relayout({"shapes": []}, [first])
    assert changed
    assert shapes == []
    _, changed = shapes_from_relayout({"shapes": []}, [])
    assert not changed


def test_moving_a_shape_edits_the_kept_shape():
    first = {"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}
    relay = {"shapes[0].x0": 2, "shapes[0].x1": 3, "shapes[0].y0": 2, "shapes[0].y1": 3}
    shapes, changed = shapes_from_relayout(relay, [first])
    assert changed
    assert shapes == [{"type": "rect", "x0": 2, "x1": 3, "y0": 2, "y1": 3}]
    # the input is not modified in place
    assert first["x0"] == 0
    # an index we do not hold is ignored
    shapes, changed = shapes_from_relayout({"shapes[3].x0": 2}, [first])
    assert not changed
    assert shapes == [first]


def test_zoom_and_shape_do_not_leak_into_each_other():
    _, axes_changed, _ = update_view_from_relayout(
        empty_view(), {"shapes": [{"type": "rect"}]}
    )
    assert not axes_changed
    shapes, changed = shapes_from_relayout(ZOOM, [])
    assert not changed
    assert shapes == []


def test_apply_view_to_figure_zoomed():
    fig = px.imshow([[1, 2], [3, 4]])
    view, _, _ = update_view_from_relayout({"dragmode": "zoom"}, ZOOM)
    shapes = [{"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}]
    apply_view_to_figure(fig, view, shapes)
    assert list(fig.layout.xaxis.range) == [153.06, 306.71]
    assert fig.layout.xaxis.autorange is False
    assert list(fig.layout.yaxis.range) == [297.77, 138.02]
    assert fig.layout.yaxis.autorange is False
    assert fig.layout.dragmode == "zoom"
    assert len(fig.layout.shapes) == 1


def test_apply_view_to_figure_default_keeps_imshow_orientation():
    fig = px.imshow([[1, 2], [3, 4]])
    fig.update_layout(dragmode="drawrect")
    apply_view_to_figure(fig, empty_view(), None)
    assert fig.layout.xaxis.range is None
    assert fig.layout.xaxis.autorange == DEFAULT_AUTORANGE["xaxis"]
    assert fig.layout.yaxis.autorange == DEFAULT_AUTORANGE["yaxis"] == "reversed"
    # no dragmode in the view leaves the figure's own
    assert fig.layout.dragmode == "drawrect"
    assert fig.layout.shapes == ()


def test_apply_axes_to_patch_zoomed():
    view, _, _ = update_view_from_relayout(empty_view(), ZOOM)
    ops = _ops(apply_axes_to_patch(Patch(), view))
    assert ops == {
        "layout.xaxis.range": [153.06, 306.71],
        "layout.xaxis.autorange": False,
        "layout.yaxis.range": [297.77, 138.02],
        "layout.yaxis.autorange": False,
    }


def test_apply_axes_to_patch_default_drops_ranges():
    ops = _ops(apply_axes_to_patch(Patch(), empty_view()))
    assert ops == {
        "layout.xaxis.autorange": True,
        "layout.xaxis.range": "Delete",
        "layout.yaxis.autorange": "reversed",
        "layout.yaxis.range": "Delete",
    }

"""The polygon selection's callbacks on the inspector page: placing and
removing corners as layout patches, submitting, showing the controls, and the
spectrum only refetching when the selection itself changes."""

import importlib
import json
from pathlib import Path

import pytest
from dash import no_update

from spectra_inspector.components.image_toolbox import (
    DRAW_POLYGON,
    IMAGE_TOOLBOX,
    POLYGON_CONTROLS_ID,
    POLYGON_NOTE_ID,
    SUBMIT_SHAPE,
)
from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.tests.test_export_summary import combined_metadata
from spectra_inspector.tests.test_image_toolbox_callbacks import (
    GRAPH_TYPE,
    _graph_ids,
    _ops,
    _processed,
)
from spectra_inspector.utilities.scaling import get_image_shape
from spectra_inspector.utilities.selection import (
    polygon_points,
    polygon_store,
    submitted_polygon,
    vertex_radius_for,
)
from spectra_inspector.utilities.view_sync import POLYGON_TOOL, empty_view

TRIANGLE = [[2.0, 1.0], [8.0, 1.0], [5.0, 6.0]]
CLICK_STORE = "polygon-click"


@pytest.fixture
def inspector(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    import dash

    from spectra_inspector.main import app  # noqa: F401

    # the module as dash imported it (``pages.inspector``): importing it again
    # under the package path registers every callback a second time
    return importlib.import_module(dash.page_registry["pages.inspector"]["module"])


@pytest.fixture
def callbacks(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app._callback_list


def _click(kind: str, x: float, y: float, n: int = 1) -> dict:
    return {"kind": kind, "x": x, "y": y, "n": n}


def _polygon_view() -> dict:
    view = empty_view()
    view["dragmode"] = POLYGON_TOOL
    return view


def test_click_adds_a_corner_on_every_built_panel(inspector):
    md = combined_metadata()
    patches, store = inspector.polygon_edit_results(
        _click("click", 3, 4), _polygon_view(), {}, _graph_ids(3), _processed(0, 2), md
    )
    assert polygon_points(store) == [[3.0, 4.0]]
    assert submitted_polygon(store) is None
    assert patches[1] is no_update
    for pos in (0, 2):
        assert _ops(patches[pos]) == {"layout.shapes": store["active_shapes"]}
    # one marker, sized from the visible extent
    (marker,) = store["active_shapes"]
    assert marker["type"] == "circle"
    assert (marker["x0"] + marker["x1"]) / 2 == pytest.approx(3.0)
    assert marker["x1"] - marker["x0"] == pytest.approx(
        2 * vertex_radius_for(inspector._visible_spans(None, md))
    )


def test_first_corner_replaces_a_box(inspector):
    box = {"active_shapes": [{"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}]}
    _, store = inspector.polygon_edit_results(
        _click("click", 3, 4),
        _polygon_view(),
        box,
        _graph_ids(1),
        _processed(0),
        md=combined_metadata(),
    )
    assert [s["type"] for s in store["active_shapes"]] == ["circle"]
    assert polygon_points(store) == [[3.0, 4.0]]
    assert inspector.selection_from_store(store) is None


def test_double_click_removes_the_nearest_corner(inspector):
    md = combined_metadata()
    store = polygon_store(TRIANGLE, None)
    # just off the second corner, within the pick tolerance of a tiny map
    patches, new_store = inspector.polygon_edit_results(
        _click("dblclick", 8.03, 1.0),
        _polygon_view(),
        store,
        _graph_ids(1),
        _processed(0),
        md,
    )
    assert polygon_points(new_store) == [TRIANGLE[0], TRIANGLE[2]]
    assert _ops(patches[0]) == {"layout.shapes": new_store["active_shapes"]}
    assert [s["type"] for s in new_store["active_shapes"]] == [
        "path",
        "circle",
        "circle",
    ]


def test_double_click_far_from_every_corner_is_a_no_op(inspector):
    md = combined_metadata()
    nrows, ncols = get_image_shape(md)
    far = (ncols * 10.0, nrows * 10.0)
    store = polygon_store(TRIANGLE, None)
    patches, new_store = inspector.polygon_edit_results(
        _click("dblclick", *far),
        _polygon_view(),
        store,
        _graph_ids(1),
        _processed(0),
        md,
    )
    assert patches == [no_update]
    assert new_store is no_update


def test_double_click_on_a_segment_inserts_a_corner(inspector):
    md = combined_metadata()
    store = polygon_store(TRIANGLE, None)
    # on the first segment, y = 1 from x = 2 to x = 8, away from both corners
    _, new_store = inspector.polygon_edit_results(
        _click("dblclick", 5.0, 1.02),
        _polygon_view(),
        store,
        _graph_ids(1),
        _processed(0),
        md,
    )
    assert polygon_points(new_store) == [TRIANGLE[0], [5.0, 1.02], *TRIANGLE[1:]]


def test_click_on_an_existing_corner_adds_nothing(inspector):
    md = combined_metadata()
    store = polygon_store(TRIANGLE, None)
    patches, new_store = inspector.polygon_edit_results(
        _click("click", 8.02, 1.0),
        _polygon_view(),
        store,
        _graph_ids(1),
        _processed(0),
        md,
    )
    assert patches == [no_update]
    assert new_store is no_update


def test_move_relocates_a_corner(inspector):
    md = combined_metadata()
    store = polygon_store(TRIANGLE, TRIANGLE)
    move = {**_click("move", 9.0, 2.0), "index": 1}
    patches, new_store = inspector.polygon_edit_results(
        move, _polygon_view(), store, _graph_ids(2), _processed(0, 1), md
    )
    assert polygon_points(new_store) == [TRIANGLE[0], [9.0, 2.0], TRIANGLE[2]]
    assert submitted_polygon(new_store) == TRIANGLE
    for patch in patches:
        assert _ops(patch) == {"layout.shapes": new_store["active_shapes"]}
    # the moved corner's marker follows it
    marker = new_store["active_shapes"][2]
    assert (marker["x0"] + marker["x1"]) / 2 == pytest.approx(9.0)
    # an index that is not a corner changes nothing
    bad = {**_click("move", 9.0, 2.0), "index": 7}
    assert inspector.polygon_edit_results(
        bad, _polygon_view(), store, _graph_ids(1), _processed(0), md
    ) == ([no_update], no_update)


def test_edits_keep_the_submitted_polygon(inspector):
    md = combined_metadata()
    store = polygon_store(TRIANGLE, TRIANGLE)
    _, new_store = inspector.polygon_edit_results(
        _click("click", 4, 4), _polygon_view(), store, _graph_ids(1), _processed(0), md
    )
    assert submitted_polygon(new_store) == TRIANGLE
    assert polygon_points(new_store) == [*TRIANGLE, [4.0, 4.0]]
    # the selection, and so the spectrum's revision, has not moved
    assert inspector._spectrum_revision("C-12", store) == inspector._spectrum_revision(
        "C-12", new_store
    )


def test_pick_tolerance_follows_the_zoom(inspector):
    md = combined_metadata()
    nrows, ncols = get_image_shape(md)
    full = inspector._visible_spans(empty_view(), md)
    assert full == (float(ncols), float(nrows))
    zoomed = empty_view()
    zoomed["xaxis"] = {"range": [1.0, 3.0]}
    zoomed["yaxis"] = {"range": [4.0, 2.0]}
    assert inspector._visible_spans(zoomed, md) == (2.0, 2.0)


def test_submit_makes_the_points_the_selection(inspector):
    store = polygon_store(TRIANGLE, None)
    submitted = inspector.submit_polygon(1, store)
    assert submitted_polygon(submitted) == TRIANGLE
    assert inspector.selection_from_store(submitted).vertices == [
        [1.0, 2.0],
        [1.0, 8.0],
        [6.0, 5.0],
    ]
    # nothing to submit: no click, too few points, or already submitted
    assert inspector.submit_polygon(None, store) is no_update
    assert inspector.submit_polygon(1, polygon_store(TRIANGLE[:2], None)) is no_update
    assert inspector.submit_polygon(1, submitted) is no_update


def test_controls_show_with_the_tool_and_enable_with_three_points(inspector):
    # (submit hidden, note hidden, submit disabled)
    toggle = inspector.toggle_polygon_controls
    assert toggle(empty_view(), {}) == (True, True, True)
    view = _polygon_view()
    assert toggle(view, {}) == (False, False, True)
    assert toggle(view, polygon_store(TRIANGLE[:2], None)) == (False, False, True)
    assert toggle(view, polygon_store(TRIANGLE, None)) == (False, False, False)
    assert toggle(view, polygon_store(TRIANGLE, TRIANGLE)) == (False, False, True)


def test_erase_drops_the_polygon_too(inspector):
    md = combined_metadata()
    store = polygon_store(TRIANGLE, TRIANGLE)
    patches, view, shapes = inspector.action_results(
        "eraseshape", _polygon_view(), store, _graph_ids(1), _processed(0), md
    )
    assert view is no_update
    assert shapes == {"active_shapes": []}
    assert _ops(patches[0]) == {"layout.shapes": []}


def test_polygon_tool_is_a_toolbox_tool():
    assert DRAW_POLYGON.id in IMAGE_TOOLBOX.tool_ids
    assert IMAGE_TOOLBOX.active_tool(_polygon_view()) == DRAW_POLYGON.id


def test_edit_callback_never_carries_figures(callbacks):
    """The edit callback only reads ids and stores: a figure State would
    upload every panel's image with each click."""
    edits = [cb for cb in callbacks if CLICK_STORE in json.dumps(cb["inputs"])]
    assert len(edits) == 1
    for dep in edits[0].get("state", []):
        assert dep["property"] != "figure"
        assert "image-container" not in json.dumps(dep["id"])
    assert GRAPH_TYPE in edits[0]["output"]


def test_no_callback_listens_to_panel_clicks(callbacks):
    """Clicks reach the click store from assets/toolbox.js, not through the
    graphs' clickData (identical clicks in a row would be deduplicated)."""
    for cb in callbacks:
        inputs = json.dumps(cb["inputs"])
        assert not ("clickData" in inputs and GRAPH_TYPE in inputs), cb["output"]


def test_click_listener_targets_the_click_store():
    js = Path(__file__).parents[1].joinpath("assets", "toolbox.js").read_text("utf-8")
    assert f'const POLYGON_CLICK_STORE = "{CLICK_STORE}";' in js
    # the polygon mode signature the listener keys on, as tool_layout sets it
    assert "fl.dragmode !== false" in js
    assert "fixedrange" in js
    for kind in ('"click"', '"dblclick"', '"move"'):
        assert kind in js
    for event in ("click", "mousedown", "mousemove", "mouseup"):
        assert f'document.addEventListener(\n  "{event}"' in js
    # the shape names the drag reads corners from, as selection.py spells them
    assert 'const POLYGON_SHAPE_NAME = "polygon";' in js
    assert 'const POLYGON_VERTEX_NAME = "polygon-vertex";' in js


def test_submit_and_controls_are_wired(callbacks):
    submit_id = IMAGE_TOOLBOX.ids.button_id(SUBMIT_SHAPE.id)
    submit = [
        cb
        for cb in callbacks
        if any(
            d["id"] == submit_id and d["property"] == "n_clicks" for d in cb["inputs"]
        )
    ]
    assert len(submit) == 1
    controls = [cb for cb in callbacks if POLYGON_CONTROLS_ID in cb["output"]]
    assert len(controls) == 1
    assert f"{POLYGON_NOTE_ID}.hidden" in controls[0]["output"]
    assert f"{submit_id}.disabled" in controls[0]["output"]

"""The shared image toolbox acts on every panel through layout patches.

A tool pick or a zoom step must go the way a dragged zoom goes: no figure is
read (every State is uploaded) and only ``Patch``es come back, so the image
data stays in the browser. The panels' own modebars are off, so the toolbox is
the only way to change tools.
"""

import importlib
import json

import numpy as np
import pytest
from dash import Patch, no_update

from spectra_inspector.components.bitmap_image import bitmap_image_layout
from spectra_inspector.components.image_toolbox import IMAGE_TOOLBOX
from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.tests.test_export_summary import combined_metadata
from spectra_inspector.user_store_model import UserStore
from spectra_inspector.utilities.scalebar_style import (
    DEFAULT_SCALEBAR_COLOR,
    DEFAULT_SCALEBAR_FONTSIZE,
)
from spectra_inspector.utilities.view_sync import empty_view

GRAPH_TYPE = "bitmap-image-graph"
TOOL_TYPE = "image-toolbox-tool"
ACTION_TYPE = "image-toolbox-action"


def _mentions(dep: dict, id_type: str, prop: str) -> bool:
    return id_type in json.dumps(dep.get("id")) and dep.get("property") == prop


def _ops(patch: Patch) -> dict[str, object]:
    result = {}
    for op in patch.to_plotly_json()["operations"]:
        loc = ".".join(str(p) for p in op["location"])
        result[loc] = op["params"].get("value", op["operation"])
    return result


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


def test_panels_have_no_native_modebar():
    card, _ = bitmap_image_layout(0)
    graphs = []

    def walk(component):
        if type(component).__name__ == "Graph":
            graphs.append(component)
        children = getattr(component, "children", None)
        for child in children if isinstance(children, list) else [children]:
            if child is not None and not isinstance(child, str):
                walk(child)

    walk(card)
    (graph,) = graphs
    assert graph.config["displayModeBar"] is False


def test_toolbox_callbacks_never_carry_figures(callbacks):
    toolbox = [
        cb
        for cb in callbacks
        if any(
            _mentions(dep, TOOL_TYPE, "n_clicks")
            or _mentions(dep, ACTION_TYPE, "n_clicks")
            for dep in cb["inputs"]
        )
    ]
    assert len(toolbox) == 2
    for cb in toolbox:
        assert GRAPH_TYPE in cb["output"]
        assert not any(_mentions(dep, GRAPH_TYPE, "figure") for dep in cb["state"])
        assert not any(_mentions(dep, GRAPH_TYPE, "figure") for dep in cb["inputs"])


def test_tool_highlight_follows_the_view_store(callbacks):
    highlighters = [
        cb
        for cb in callbacks
        if TOOL_TYPE in cb["output"] and cb["output"].endswith(".active")
    ]
    assert len(highlighters) == 1
    (highlighter,) = highlighters
    assert [dep["id"] for dep in highlighter["inputs"]] == ["image-view-store"]


def _graph_ids(n: int) -> list[dict]:
    return [{"type": GRAPH_TYPE, "index": i} for i in range(n)]


def _processed(*indices: int) -> dict:
    return {"graph_ids": [{"type": GRAPH_TYPE, "index": i} for i in indices]}


def test_scalebar_controls_restyle_built_panels_and_fill_the_store(inspector):
    # the controls' values, validated, land in the store and on every built
    # panel as a layout patch; a panel without a figure yet is left alone
    patches, store = inspector.restyle_scalebar(
        False, "#ff0000", "16", _graph_ids(3), _processed(0, 2)
    )
    assert store == {"show": False, "color": "#ff0000", "fontsize": 16}
    assert patches[1] is no_update
    expected = {
        "data.1.visible": False,
        "data.1.line.color": "#ff0000",
        "layout.annotations.0.visible": False,
        "layout.annotations.0.font.color": "#ff0000",
        "layout.annotations.0.font.size": 16,
    }
    assert _ops(patches[0]) == expected
    assert _ops(patches[2]) == expected
    # a value the controls could not report means the default
    _, store = inspector.restyle_scalebar(None, "red", None, _graph_ids(0), {})
    assert store == {
        "show": True,
        "color": DEFAULT_SCALEBAR_COLOR,
        "fontsize": DEFAULT_SCALEBAR_FONTSIZE,
    }


def test_scalebar_callback_never_carries_figures(callbacks):
    restylers = [
        cb
        for cb in callbacks
        if any(dep["id"] == "image-toolbox-scalebar-color" for dep in cb["inputs"])
    ]
    assert len(restylers) == 1
    (restyler,) = restylers
    assert GRAPH_TYPE in restyler["output"]
    assert "scalebar-style.data" in restyler["output"]
    assert not any(_mentions(dep, GRAPH_TYPE, "figure") for dep in restyler["state"])


def test_tool_patches_only_built_panels(inspector):
    patches, view = inspector.tool_patches("pan", None, _graph_ids(3), _processed(0, 2))
    assert view["dragmode"] == "pan"
    assert view["xaxis"] is None
    assert patches[1] is no_update
    expected = {
        "layout.dragmode": "pan",
        "layout.xaxis.fixedrange": False,
        "layout.yaxis.fixedrange": False,
    }
    assert _ops(patches[0]) == expected
    assert _ops(patches[2]) == expected


def test_polygon_tool_switches_dragging_off(inspector):
    patches, view = inspector.tool_patches(
        "drawpolygon", None, _graph_ids(1), _processed(0)
    )
    assert view["dragmode"] == "drawpolygon"
    assert _ops(patches[0]) == {
        "layout.dragmode": False,
        "layout.xaxis.fixedrange": True,
        "layout.yaxis.fixedrange": True,
    }


def test_tool_patches_keep_the_zoom(inspector):
    zoomed = {"dragmode": "zoom", "xaxis": {"range": [1.0, 2.0]}, "yaxis": None}
    _, view = inspector.tool_patches("drawrect", zoomed, _graph_ids(1), _processed(0))
    assert view == {
        "dragmode": "drawrect",
        "xaxis": {"range": [1.0, 2.0]},
        "yaxis": None,
    }


def test_default_tool_is_what_new_figures_get(inspector):
    # a view without a dragmode leaves a fresh figure on get_new_im's default,
    # which is the tool the toolbox shows pressed for that view
    fig = inspector.get_new_im(
        UserStore(),
        (0.0, 1.0),
        "turbo",
        im_data=np.zeros((2, 2)),
        md=combined_metadata(),
    )
    assert fig.layout.dragmode == IMAGE_TOOLBOX.default_tool
    assert IMAGE_TOOLBOX.default_tool in IMAGE_TOOLBOX.tool_ids


def test_zoom_in_from_the_full_image(inspector):
    md = combined_metadata()  # a 2 x 2 map
    patches, view, shapes = inspector.action_results(
        "zoomin",
        empty_view(),
        {"active_shapes": []},
        _graph_ids(2),
        _processed(0, 1),
        md,
    )
    assert shapes is no_update
    # the full image spans -0.5 .. 1.5 on x and 1.5 .. -0.5 on the reversed y;
    # halving about the centre gives the middle pixel edges
    assert view["xaxis"] == {"range": [0.0, 1.0]}
    assert view["yaxis"] == {"range": [1.0, 0.0]}
    for patch in patches:
        ops = _ops(patch)
        assert ops["layout.xaxis.range"] == [0.0, 1.0]
        assert ops["layout.xaxis.autorange"] is False
        assert ops["layout.yaxis.range"] == [1.0, 0.0]
        # the scalebar is re-sized to the new view
        assert "data.1" in ops
        assert "layout.annotations.0" in ops


def test_zoom_out_doubles_the_current_view(inspector):
    md = combined_metadata()
    zoomed = {
        "dragmode": "zoom",
        "xaxis": {"range": [0.0, 1.0]},
        "yaxis": {"range": [1.0, 0.0]},
    }
    _, view, _ = inspector.action_results(
        "zoomout", zoomed, None, _graph_ids(1), _processed(0), md
    )
    assert view["dragmode"] == "zoom"
    assert view["xaxis"] == {"range": [-0.5, 1.5]}
    assert view["yaxis"] == {"range": [1.5, -0.5]}


def test_erase_drops_the_box_everywhere(inspector):
    md = combined_metadata()
    box = {"active_shapes": [{"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}]}
    patches, view, shapes = inspector.action_results(
        "eraseshape", empty_view(), box, _graph_ids(2), _processed(0, 1), md
    )
    assert view is no_update
    assert shapes == {"active_shapes": []}
    assert all(_ops(patch) == {"layout.shapes": []} for patch in patches)


def test_erase_with_no_box_is_a_no_op(inspector):
    md = combined_metadata()
    patches, view, shapes = inspector.action_results(
        "eraseshape",
        empty_view(),
        {"active_shapes": []},
        _graph_ids(1),
        _processed(0),
        md,
    )
    assert patches == [no_update]
    assert view is no_update
    assert shapes is no_update


def test_actions_wait_for_a_built_panel(inspector):
    md = combined_metadata()
    patches, view, shapes = inspector.action_results(
        "zoomin", empty_view(), None, _graph_ids(2), {"initialized": False}, md
    )
    assert patches == [no_update, no_update]
    assert view is no_update
    assert shapes is no_update

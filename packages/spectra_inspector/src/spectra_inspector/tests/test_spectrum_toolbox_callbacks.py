"""The spectrum toolbox: the tool goes through the server as a layout patch
and is kept on every rebuilt figure; the zoom steps and the reset are
clientside relayouts on the plot's live ranges. Nothing uploads the spectrum
figure."""

import importlib
import json
from contextvars import copy_context

import pytest
from dash import Patch, no_update
from dash._callback_context import context_value
from dash._utils import AttributeDict

from spectra_inspector.components.spectrum_toolbox import SPECTRUM_TOOLBOX
from spectra_inspector.settings import ENV_PREFIX

SPECTRUM = "spectrum-container"
TOOL_TYPE = "spectrum-toolbox-tool"
ACTION_TYPE = "spectrum-toolbox-action"
RESET = "spectrum-toolbox-reset"
VIEW_STORE = "spectrum-view"


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

    return importlib.import_module(dash.page_registry["pages.inspector"]["module"])


@pytest.fixture
def callbacks(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app._callback_list


def test_tool_callback_never_carries_the_figure(callbacks):
    tool_callbacks = [
        cb
        for cb in callbacks
        if any(_mentions(dep, TOOL_TYPE, "n_clicks") for dep in cb["inputs"])
    ]
    assert len(tool_callbacks) == 1
    (cb,) = tool_callbacks
    assert f"{SPECTRUM}.figure" in cb["output"]
    assert VIEW_STORE in cb["output"]
    assert not any(dep.get("id") == SPECTRUM for dep in cb["state"] + cb["inputs"])


def test_tool_highlight_follows_the_store(callbacks):
    highlighters = [
        cb
        for cb in callbacks
        if TOOL_TYPE in cb["output"] and cb["output"].endswith(".active")
    ]
    assert len(highlighters) == 1
    assert [dep["id"] for dep in highlighters[0]["inputs"]] == [VIEW_STORE]


def test_actions_and_reset_are_one_clientside_callback(callbacks):
    actions = [
        cb
        for cb in callbacks
        if any(_mentions(dep, ACTION_TYPE, "n_clicks") for dep in cb["inputs"])
    ]
    assert len(actions) == 1
    (cb,) = actions
    assert cb["clientside_function"] == {
        "namespace": "toolbox",
        "function_name": "spectrumAction",
    }
    assert any(dep.get("id") == RESET for dep in cb["inputs"])
    assert not any(dep["property"] == "figure" for dep in cb["state"] + cb["inputs"])


def test_new_figures_carry_the_tool(inspector):
    fig = inspector.new_spectrum_figure([0.0, 1.0], [1.0, 2.0], dragmode="pan")
    assert fig.layout.dragmode == "pan"
    fig = inspector.new_spectrum_figure([0.0, 1.0], [1.0, 2.0])
    assert fig.layout.dragmode == SPECTRUM_TOOLBOX.default_tool


def test_figures_carry_a_revision_that_follows_the_spectrum_shown(inspector):
    box = {"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}
    full = inspector._spectrum_revision("C12", {"active_shapes": []})
    assert full == inspector._spectrum_revision("C12", None)
    assert full != inspector._spectrum_revision("C12", {"active_shapes": [box]})
    assert full != inspector._spectrum_revision("C8", {"active_shapes": []})
    fig = inspector.new_spectrum_figure([0.0, 1.0], [1.0, 2.0], uirevision=full)
    assert fig.layout.uirevision == full
    # a rebuild keeps it: the figure dict is what dash-renderer holds
    kept = inspector._with_spectrum_dragmode(
        {"data": [], "layout": {"uirevision": full}}, {"dragmode": "pan"}
    )
    assert kept["layout"]["uirevision"] == full


def test_yaxis_scale_change_resets_only_the_y_axis(inspector):
    patch = inspector.set_spectrum_yaxis_scale("log", {"data": [], "layout": {}})
    assert _ops(patch) == {
        "layout.yaxis.type": "log",
        "layout.yaxis.uirevision": "log",
    }
    assert inspector.set_spectrum_yaxis_scale("log", None) is no_update


def test_replacement_figures_carry_the_stored_tool(inspector):
    figure = {"data": [], "layout": {"xaxis": {"title": "x"}}}
    out = inspector._with_spectrum_dragmode(figure, {"dragmode": "pan"})
    assert out["layout"]["dragmode"] == "pan"
    assert out["layout"]["xaxis"] == {"title": "x"}
    out = inspector._with_spectrum_dragmode({"data": []}, None)
    assert out["layout"]["dragmode"] == SPECTRUM_TOOLBOX.default_tool


def _click(inspector, tool: str, *args):
    prop_id = json.dumps(
        {"index": tool, "type": TOOL_TYPE}, separators=(",", ":"), sort_keys=True
    )
    triggered = [{"prop_id": f"{prop_id}.n_clicks", "value": 1}]

    def run():
        context_value.set(AttributeDict(triggered_inputs=triggered))
        return inspector.select_spectrum_tool([1, 0], *args)

    return copy_context().run(run)


def test_selecting_a_tool_patches_the_dragmode_and_writes_the_store(inspector):
    patch, view = _click(inspector, "pan", {"energy": [0.0]}, None)
    assert _ops(patch) == {"layout.dragmode": "pan"}
    assert view == {"dragmode": "pan"}


def test_selecting_a_tool_before_the_figure_exists_only_writes_the_store(inspector):
    patch, view = _click(inspector, "pan", {}, {"dragmode": None})
    assert patch is no_update
    assert view == {"dragmode": "pan"}


def test_reselecting_the_current_tool_is_a_no_op(inspector):
    assert _click(inspector, "zoom", {"energy": [0.0]}, None) == (no_update, no_update)
    assert _click(inspector, "pan", {"energy": [0.0]}, {"dragmode": "pan"}) == (
        no_update,
        no_update,
    )

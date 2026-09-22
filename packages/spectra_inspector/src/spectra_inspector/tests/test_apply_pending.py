"""The Apply buttons say when they need pressing.

A change to a panel's controls marks its Apply in the browser
(``assets/apply_button.js``, styled by ``assets/layout.css``) and the figure
builder that answers the click puts the idle props back. What python can
check: the clientside callbacks are wired to the right props, the script and
the stylesheet spell the same names as the python constants, and the builders
send the button props back with the figure.
"""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import dash
import numpy as np
import pytest
from dash import no_update

from spectra_inspector.components.energy_range_slider import (
    APPLY_IDLE_PROPS,
    APPLY_PENDING_PROPS,
)
from spectra_inspector.settings import ENV_PREFIX

SINGLE_APPLY = "element-dropdown-slider-refreshbutton"
SINGLE_CONTROLS = ("element-dropdown-slider-dropdown", "element-dropdown-slider-slider")
COMPOSITE_APPLY = "composite-image-apply"
CHANNEL_CONTROLS = (
    "composite-channel-selector-dropdown",
    "composite-channel-selector-slider",
    "composite-channel-color",
    "composite-channel-stretch",
)
GRAPH_TYPE = "bitmap-image-graph"
DIV_TYPE = "bitmap-image-div"
ASSETS = Path(__file__).parents[1] / "assets"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app


@pytest.fixture
def callbacks(app):
    return app._callback_list


@pytest.fixture
def inspector(app):  # noqa: ARG001
    return importlib.import_module(dash.page_registry["pages.inspector"]["module"])


@pytest.fixture
def triggered_by(mocker, inspector):
    def _set(triggered_id, n_props: int = 1):
        mocker.patch.object(
            type(inspector.ctx),
            "triggered_id",
            new_callable=mocker.PropertyMock,
            return_value=triggered_id,
        )
        mocker.patch.object(
            type(inspector.ctx),
            "triggered_prop_ids",
            new_callable=mocker.PropertyMock,
            return_value={f"prop{i}": triggered_id for i in range(n_props)},
        )

    return _set


def _outputs(cb: dict) -> list[tuple[dict | str, str]]:
    """The (id, prop) pairs a callback writes, however dash serialised them."""
    output = cb["output"]
    specs = output[2:-2].split("...") if output.startswith("..") else [output]
    pairs = []
    for spec in specs:
        id_str, _, prop = spec.split("@", maxsplit=1)[0].rpartition(".")
        pairs.append((json.loads(id_str) if id_str.startswith("{") else id_str, prop))
    return pairs


def _writer_of(callbacks, id_type: str) -> dict:
    writers = [
        cb
        for cb in callbacks
        if any(
            isinstance(id_, dict) and id_.get("type") == id_type
            for id_, _ in _outputs(cb)
        )
    ]
    assert len(writers) == 1, [cb["output"] for cb in writers]
    return writers[0]


def _deps(cb: dict, key: str) -> set[tuple[str, str, str]]:
    deps = set()
    for dep in cb.get(key, []):
        id_ = json.loads(dep["id"]) if isinstance(dep["id"], str) else dep["id"]
        deps.add((id_["type"], json.dumps(id_["index"]), dep["property"]))
    return deps


def test_single_panel_controls_mark_their_own_apply(callbacks):
    marker = _writer_of(callbacks, SINGLE_APPLY)
    assert marker["clientside_function"]["namespace"] == "applyButton"
    assert marker["prevent_initial_call"]
    assert {(id_["index"][0], prop) for id_, prop in _outputs(marker)} == {
        ("MATCH", "color"),
        ("MATCH", "className"),
    }
    assert _deps(marker, "inputs") == {
        (control, '["MATCH"]', "value") for control in SINGLE_CONTROLS
    }


def test_composite_channel_controls_mark_their_panels_apply(callbacks):
    marker = _writer_of(callbacks, COMPOSITE_APPLY)
    assert marker["clientside_function"]["namespace"] == "applyButton"
    assert marker["prevent_initial_call"]
    assert {(id_["index"][0], prop) for id_, prop in _outputs(marker)} == {
        ("ALL", "color"),
        ("ALL", "className"),
    }
    assert _deps(marker, "inputs") == {
        (control, '["ALL"]', "value") for control in CHANNEL_CONTROLS
    }
    # the script matches the triggered channel to its panel's Apply by id
    assert _deps(marker, "state") == {(COMPOSITE_APPLY, '["ALL"]', "id")}


def test_the_browser_side_spells_the_same_names():
    js = ASSETS.joinpath("apply_button.js").read_text("utf-8")
    assert f'const APPLY_PENDING_COLOR = "{APPLY_PENDING_PROPS["color"]}";' in js
    assert f'const APPLY_PENDING_CLASS = "{APPLY_PENDING_PROPS["className"]}";' in js
    assert "applyButton: {" in js
    for name in ("markPending", "markPanelPending"):
        assert f"{name}: function" in js

    css = ASSETS.joinpath("layout.css").read_text("utf-8")
    assert f".{APPLY_PENDING_PROPS['className']} {{" in css
    assert "animation:" in css
    assert "prefers-reduced-motion" in css


def _graph(index: int) -> dict:
    return {"type": GRAPH_TYPE, "index": index}


def _single_panel_args(refresh_ids, fig_list, processed):
    graph_ids = [_graph(id_["index"]) for id_ in refresh_ids]
    return {
        "n_clicks": [None] * len(refresh_ids),
        "reset_nclicks": None,
        "refresh_ids": refresh_ids,
        "colormap_choices": ["viridis"] * len(refresh_ids),
        "graph_id_store": {
            "active_div_ids": [
                {"type": DIV_TYPE, "index": id_["index"]} for id_ in refresh_ids
            ]
        },
        "slider_range_list": [[1.0, 2.0]] * len(refresh_ids),
        "graph_ids": graph_ids,
        "user_store_dict": {"selected_dataset": "sample"},
        "processed_graph_store": {"graph_ids": [_graph(i) for i in processed]},
        "sample_name": "sample",
        "fig_list": fig_list,
        "view_store": None,
        "shapes_store": None,
    }


def test_a_refresh_puts_the_apply_back(inspector, mocker, triggered_by):
    refresh_ids = [{"type": SINGLE_APPLY, "index": i} for i in (0, 1)]
    set_props = mocker.patch.object(inspector, "set_props")
    mocker.patch.object(inspector, "get_new_im", return_value={"refreshed": True})
    triggered_by(refresh_ids[1])

    figs, processed, view = inspector.update_graph_figure(
        **_single_panel_args(refresh_ids, [{}, {}], processed=(0, 1))
    )

    assert figs == [no_update, {"refreshed": True}]
    assert processed is no_update
    assert view is no_update
    assert set_props.call_args_list == [mocker.call(refresh_ids[1], APPLY_IDLE_PROPS)]


def test_a_later_panel_fetches_its_own_image_and_is_not_marked(
    inspector, mocker, monkeypatch, triggered_by
):
    refresh_ids = [{"type": SINGLE_APPLY, "index": i} for i in (0, 3)]
    set_props = mocker.patch.object(inspector, "set_props")
    mocker.patch.object(inspector, "get_new_im", return_value={"fetched": True})
    fetch = mocker.patch.object(
        inspector, "fetch_im_data_parallel", return_value=[np.zeros((4, 4))]
    )
    monkeypatch.setattr(
        inspector.UserStore, "conditionally_fetch_metadata", lambda _self: object()
    )
    triggered_by(refresh_ids[1])

    figs, processed, _ = inspector.update_graph_figure(
        **_single_panel_args(refresh_ids, [{"data": [{"type": "heatmap"}]}, {}], (0,))
    )

    assert figs == [no_update, {"fetched": True}]
    assert _graph(3) in processed["graph_ids"]
    fetch.assert_called_once()
    assert fetch.call_args.args[1] == [[1.0, 2.0]]
    assert not any(
        call.args[1] == APPLY_PENDING_PROPS for call in set_props.call_args_list
    )


def test_the_composite_apply_goes_back_when_clicked(
    inspector, mocker, monkeypatch, triggered_by
):
    apply_id = {"type": COMPOSITE_APPLY, "index": 0}
    set_props = mocker.patch.object(inspector, "set_props")
    mocker.patch.object(inspector, "get_composite_im", return_value={"blend": True})
    monkeypatch.setattr(
        inspector.UserStore,
        "conditionally_fetch_metadata",
        lambda _self: SimpleNamespace(data_shape=(4, 4, 10)),
    )
    triggered_by(apply_id)

    figs, processed = inspector.update_composite_figure(
        n_clicks=[1],
        apply_ids=[apply_id],
        channel_elements=[],
        channel_element_ids=[],
        channel_ranges=[],
        channel_range_ids=[],
        channel_colors=[],
        channel_color_ids=[],
        channel_stretches=[],
        channel_stretch_ids=[],
        graph_id_store={"active_div_ids": [{"type": DIV_TYPE, "index": 0}]},
        graph_ids=[_graph(0)],
        user_store_dict={"selected_dataset": "sample"},
        processed_graph_store={"graph_ids": [_graph(0)]},
        sample_name="sample",
        view_store=None,
        shapes_store=None,
    )

    assert figs == [{"blend": True}]
    assert processed is no_update
    assert mocker.call(apply_id, APPLY_IDLE_PROPS) in set_props.call_args_list

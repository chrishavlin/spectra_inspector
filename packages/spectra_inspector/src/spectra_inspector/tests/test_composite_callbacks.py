"""The multi-channel panel's wiring on the inspector page.

The composite reuses the ``bitmap-image`` graph, so the view syncing and the
box tool never learn about it; what is new is a second figure-building
callback keyed on the composite's Apply, the mode switch that replaces every
panel, and the export reading the channel controls. The guards here mirror
those of ``test_image_panel_patches``: the figure builders never read the
figures they do not need, and the panel container is never read back.
"""

import importlib
import json

import dash
import pytest

from spectra_inspector.settings import ENV_PREFIX

GRAPH_TYPE = "bitmap-image-graph"
COMPOSITE_APPLY = "composite-image-apply"
CHANNEL_DROPDOWN = "composite-channel-selector-dropdown"
CHANNEL_COLOR = "composite-channel-color"
MODE = "image-mode"
CONTAINER = "image-container"
ADD_BUTTON = "dynamic-add-image-btn"


def _mentions(dep: dict, id_type: str, prop: str) -> bool:
    return id_type in json.dumps(dep.get("id")) and dep.get("property") == prop


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
    # the page module as Dash registered it (a plain import would register
    # every callback a second time)
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


def test_composite_apply_has_its_own_builder_that_reads_no_figures(callbacks):
    builders = [
        cb
        for cb in callbacks
        if any(_mentions(dep, COMPOSITE_APPLY, "n_clicks") for dep in cb["inputs"])
    ]
    assert len(builders) == 1
    (builder,) = builders
    assert GRAPH_TYPE in builder["output"]
    assert "processed-graph-ids" in builder["output"]
    assert not any(dep["property"] == "figure" for dep in builder["state"])
    assert not any(dep["property"] == "relayoutData" for dep in builder["inputs"])
    assert any(_mentions(dep, CHANNEL_DROPDOWN, "value") for dep in builder["state"])
    assert any(_mentions(dep, CHANNEL_COLOR, "value") for dep in builder["state"])


def test_the_single_panel_builder_knows_which_panels_are_its_own(callbacks):
    builders = [
        cb
        for cb in callbacks
        if any(dep.get("id") == "reset-all-axes" for dep in cb["inputs"])
    ]
    (builder,) = builders
    assert any(
        _mentions(dep, "element-dropdown-slider-refreshbutton", "id")
        for dep in builder["state"]
    )
    assert not any(
        _mentions(dep, COMPOSITE_APPLY, "n_clicks") for dep in builder["inputs"]
    )


def test_mode_switch_replaces_the_panels_without_reading_them(callbacks):
    switches = [
        cb
        for cb in callbacks
        if any(
            dep.get("id") == MODE and dep["property"] == "value" for dep in cb["inputs"]
        )
    ]
    assert len(switches) == 1
    (switch,) = switches
    for output in (CONTAINER, "graph-id-store", "processed-graph-ids"):
        assert output in switch["output"]
    assert not any(dep.get("id") == CONTAINER for dep in switch["state"])


def test_adding_a_panel_reads_the_mode(callbacks):
    adders = [
        cb
        for cb in callbacks
        if any(
            dep.get("id") == ADD_BUTTON and dep["property"] == "n_clicks"
            for dep in cb["inputs"]
        )
    ]
    (adder,) = adders
    assert any(dep.get("id") == MODE for dep in adder["state"])
    assert not any(dep.get("id") == CONTAINER for dep in adder["state"])


def test_export_reads_the_channel_controls(callbacks):
    exporters = [cb for cb in callbacks if "downloadsummary" in cb["output"]]
    assert len(exporters) == 1
    (exporter,) = exporters
    for id_type, prop in (
        (GRAPH_TYPE, "id"),
        (COMPOSITE_APPLY, "id"),
        (CHANNEL_DROPDOWN, "value"),
        (CHANNEL_DROPDOWN, "id"),
        (CHANNEL_COLOR, "value"),
        ("composite-channel-stretch", "value"),
    ):
        assert any(_mentions(dep, id_type, prop) for dep in exporter["state"])


class TestSwitchImageMode:
    def test_multi_opens_one_composite(self, inspector):
        children, graph_store, processed = inspector.switch_image_mode(
            inspector.IMAGE_MODE_MULTI, "C-12", {}, False
        )
        assert len(children) == 1
        assert children[0].id == {"type": "bitmap-image-div", "index": 0}
        assert graph_store == {
            "initialized": True,
            "active_div_ids": [{"type": "bitmap-image-div", "index": 0}],
            "next_index": 1,
        }
        assert processed == {"initialized": False}
        ids = repr(children[0])
        assert "composite-image-apply" in ids
        assert "element-dropdown-slider" not in ids

    def test_single_reopens_the_usual_panels(self, inspector):
        children, graph_store, _ = inspector.switch_image_mode(
            inspector.IMAGE_MODE_SINGLE, "C-12", {}, False
        )
        assert len(children) == inspector.NUMBER_OF_INITIAL_FIGURES
        assert graph_store["next_index"] == inspector.NUMBER_OF_INITIAL_FIGURES
        ids = repr(children[0])
        assert "element-dropdown-slider-refreshbutton" in ids
        assert "composite-image-apply" not in ids

    def test_nothing_happens_without_a_map(self, inspector):
        nothing = (inspector.no_update,) * 3
        assert (
            inspector.switch_image_mode(inspector.IMAGE_MODE_MULTI, "none", {}, False)
            == nothing
        )
        assert (
            inspector.switch_image_mode(
                inspector.IMAGE_MODE_MULTI, "C-12", {"spectrum_only": True}, False
            )
            == nothing
        )


class TestAddOrDeleteImage:
    def _added(self, patch) -> int:
        ops = patch.to_plotly_json()["operations"]
        assert all(op["operation"] == "Append" for op in ops)
        return len(ops)

    def test_first_batch_in_multi_mode_is_one_composite(self, inspector, triggered_by):
        triggered_by(inspector._IDS.add_image)
        patch, store = inspector.add_or_delete_image(
            3, [], {"initialized": False}, inspector.IMAGE_MODE_MULTI
        )
        assert self._added(patch) == 1
        assert store["next_index"] == 1
        assert store["active_div_ids"] == [{"type": "bitmap-image-div", "index": 0}]

    def test_first_batch_in_single_mode_is_three(self, inspector, triggered_by):
        triggered_by(inspector._IDS.add_image)
        patch, store = inspector.add_or_delete_image(
            3, [], {"initialized": False}, inspector.IMAGE_MODE_SINGLE
        )
        assert self._added(patch) == 3
        assert store["next_index"] == 3

    def test_later_panels_take_the_next_index(self, inspector, triggered_by):
        triggered_by(inspector._IDS.add_image)
        store = {
            "initialized": True,
            "active_div_ids": [{"type": "bitmap-image-div", "index": 0}],
            "next_index": 1,
        }
        patch, store = inspector.add_or_delete_image(
            9, [], store, inspector.IMAGE_MODE_MULTI
        )
        assert self._added(patch) == 1
        assert store["active_div_ids"][-1] == {"type": "bitmap-image-div", "index": 1}
        assert store["next_index"] == 2

"""Guard the image-panel callbacks that must not carry figures.

A colormap pick and a panel deletion are answered with a ``Patch``: the image
data stays in the browser. Both would silently regress if the colorscale
dropdown became an input of the figure-building callback again, or if the
add/delete callback read the container's children back (dash-renderer serves
States from its layout store, so that value carries every panel's figure).
"""

import json

import numpy as np
import plotly.express as px
import pytest

from spectra_inspector.components.bitmap_image import colorscale_patch
from spectra_inspector.settings import ENV_PREFIX

GRAPH_TYPE = "bitmap-image-graph"
COLORSCALE_TYPE = "bitmap-image-colorscale"
CONTAINER = "image-container"
ADD_BUTTON = "dynamic-add-image-btn"
RESET_BUTTON = "reset-all-axes"


def _mentions(dep: dict, id_type: str, prop: str) -> bool:
    return id_type in json.dumps(dep.get("id")) and dep.get("property") == prop


@pytest.fixture
def callbacks(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app._callback_list


def test_colorscale_patch_matches_what_imshow_emits():
    fig = px.imshow(np.arange(6).reshape(2, 3), color_continuous_scale="turbo")
    expected = fig.to_plotly_json()["layout"]["coloraxis"]["colorscale"]

    (op,) = colorscale_patch("turbo").to_plotly_json()["operations"]
    assert op["operation"] == "Assign"
    assert op["location"] == ["layout", "coloraxis", "colorscale"]
    got = op["params"]["value"]
    assert [color for _, color in got] == [color for _, color in expected]
    assert [pos for pos, _ in got] == pytest.approx([pos for pos, _ in expected])


def test_recolor_is_answered_without_touching_figures(callbacks):
    recolor_callbacks = [
        cb
        for cb in callbacks
        if any(_mentions(dep, COLORSCALE_TYPE, "value") for dep in cb["inputs"])
    ]
    assert len(recolor_callbacks) == 1
    (recolor,) = recolor_callbacks
    assert GRAPH_TYPE in recolor["output"]
    assert len(recolor["inputs"]) == 1
    assert not any(dep["property"] == "figure" for dep in recolor["state"])


def test_figure_builder_reads_the_colorscale_as_state(callbacks):
    builders = [
        cb
        for cb in callbacks
        if any(dep.get("id") == RESET_BUTTON for dep in cb["inputs"])
    ]
    assert len(builders) == 1
    (builder,) = builders
    assert not any(
        _mentions(dep, COLORSCALE_TYPE, "value") for dep in builder["inputs"]
    )
    assert any(_mentions(dep, COLORSCALE_TYPE, "value") for dep in builder["state"])


def test_panel_add_and_delete_never_read_the_container(callbacks):
    adders = [
        cb
        for cb in callbacks
        if any(
            dep.get("id") == ADD_BUTTON and dep["property"] == "n_clicks"
            for dep in cb["inputs"]
        )
    ]
    assert len(adders) == 1
    (adder,) = adders
    assert CONTAINER in adder["output"]
    assert not any(dep.get("id") == CONTAINER for dep in adder["state"])

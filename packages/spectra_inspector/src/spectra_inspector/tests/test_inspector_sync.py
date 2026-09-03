"""Guard the split between the two inspector figure callbacks.

Zooms, tool changes and box annotations arrive as relayoutData and must be
answered by a callback that neither reads nor returns whole figures: every
State of a callback is uploaded with the request, and the image panels carry
the image data. Shipping them on every zoom is what made syncing slow, and
reading the zoom off them is what broke it (issue #65) -- the figure prop
never carries plotly's ranges.
"""

import json

import pytest

from spectra_inspector.settings import ENV_PREFIX

GRAPH_TYPE = "bitmap-image-graph"


def _mentions(dep: dict, id_type: str, prop: str) -> bool:
    return id_type in json.dumps(dep.get("id")) and dep.get("property") == prop


@pytest.fixture
def callbacks(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app._callback_list


def test_relayout_is_answered_without_touching_figures(callbacks):
    relayout_callbacks = [
        cb
        for cb in callbacks
        if any(_mentions(dep, GRAPH_TYPE, "relayoutData") for dep in cb["inputs"])
    ]
    assert len(relayout_callbacks) == 1
    (sync,) = relayout_callbacks
    assert not any(_mentions(dep, GRAPH_TYPE, "figure") for dep in sync["state"])
    assert not any(_mentions(dep, GRAPH_TYPE, "figure") for dep in sync["inputs"])
    assert GRAPH_TYPE in sync["output"]
    assert "image-view-store" in sync["output"]
    assert "active-shapes" in sync["output"]


def test_figure_building_callback_does_not_listen_to_relayout(callbacks):
    heavy = [
        cb
        for cb in callbacks
        if any(_mentions(dep, GRAPH_TYPE, "figure") for dep in cb["state"])
        and GRAPH_TYPE in cb["output"]
    ]
    assert heavy, "the figure-building callback should still read the figures"
    for cb in heavy:
        assert not any(
            _mentions(dep, GRAPH_TYPE, "relayoutData") for dep in cb["inputs"]
        )

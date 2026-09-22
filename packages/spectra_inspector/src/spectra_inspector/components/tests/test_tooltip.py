"""Hover tooltips carry an id the browser-side sweeper can resolve to the
target element (``assets/hover_tooltip.js``)."""

from pathlib import Path

import dash_bootstrap_components as dbc
import pytest
from dash._utils import stringify_id

from spectra_inspector.components.bitmap_image import bitmap_image_layout
from spectra_inspector.components.composite_image import composite_image_layout
from spectra_inspector.components.image_toolbox import image_toolbox_layout
from spectra_inspector.components.spectrum_toolbox import spectrum_toolbox_layout
from spectra_inspector.components.tooltip import (
    HOVER_TOOLTIP_TYPE,
    dom_id,
    hover_tooltip,
    hover_tooltip_id,
)

ASSETS = Path(__file__).parents[2] / "assets"


@pytest.mark.parametrize(
    "target",
    ["plain-id", {"type": "demo", "index": 3}, {"index": "a-b", "type": "demo"}],
)
def test_dom_id_matches_what_dash_renders(target):
    assert dom_id(target) == stringify_id(target)


def test_hover_tooltip_is_hover_only_and_names_its_target():
    tip = hover_tooltip("hint", {"type": "demo", "index": 0}, placement="bottom")
    assert isinstance(tip, dbc.Tooltip)
    assert tip.trigger == "hover"
    assert tip.placement == "bottom"
    assert tip.id == {"type": HOVER_TOOLTIP_TYPE, "index": '{"index":0,"type":"demo"}'}
    assert tip.id == hover_tooltip_id({"index": 0, "type": "demo"})


def test_a_caller_may_pick_the_id():
    tip = hover_tooltip("hint", "demo", id="my-tip")
    assert tip.id == "my-tip"


def _tooltips(component):
    return [c for c in component._traverse() if isinstance(c, dbc.Tooltip)]


@pytest.mark.parametrize(
    "build",
    [
        lambda: bitmap_image_layout(0)[0],
        lambda: composite_image_layout(0)[0],
        lambda: image_toolbox_layout()[0],
        lambda: spectrum_toolbox_layout([])[1],
    ],
)
def test_every_layout_tooltip_resolves_to_one_of_its_targets(build):
    """One tooltip per target, and each tooltip's index is the DOM id of a
    component in the same layout, so the sweeper's getElementById finds it."""
    layout = build()
    tooltips = _tooltips(layout)
    assert tooltips
    present = {dom_id(c.id) for c in layout._traverse() if getattr(c, "id", None)}
    ids = [stringify_id(t.id) for t in tooltips]
    assert len(set(ids)) == len(ids)
    for tip in tooltips:
        assert tip.trigger == "hover"
        assert tip.id["type"] == HOVER_TOOLTIP_TYPE
        assert tip.id["index"] == dom_id(tip.target)
        assert tip.id["index"] in present


def test_the_browser_side_spells_the_same_type():
    js = ASSETS.joinpath("hover_tooltip.js").read_text("utf-8")
    assert f'const HOVER_TOOLTIP_TYPE = "{HOVER_TOOLTIP_TYPE}";' in js
    assert 'new MouseEvent("mouseout", { bubbles: false })' in js
    assert "MutationObserver" in js

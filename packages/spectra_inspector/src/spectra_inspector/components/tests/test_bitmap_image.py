import dash_bootstrap_components as dbc
from matplotlib import colormaps

from spectra_inspector.components.bitmap_image import bitmap_image_layout
from spectra_inspector.utilities.coerce import get_sequential_colorscales


def test_bitmap_image_layout():

    _, div_ids = bitmap_image_layout(0)
    for prop in div_ids.prop_names:
        assert prop in getattr(div_ids, prop)
        assert div_ids.get_id_with_index(prop)["index"] == 0


def test_panel_tooltips_follow_the_mouse_only():
    """A focus-triggered tooltip outlives the mouse: the element dropdown hands
    focus back to its button after a pick and the tooltip stays until a blur."""
    card, _ = bitmap_image_layout(0)
    tooltips = [c for c in card._traverse() if isinstance(c, dbc.Tooltip)]
    assert len(tooltips) == 5
    assert {t.trigger for t in tooltips} == {"hover"}


def test_get_sequential_colorscales_restrict_to_common():
    restricted = get_sequential_colorscales(restrict_to_common=True)

    assert restricted
    assert {name.lower() for name in restricted}.issubset(
        {name.lower() for name in colormaps}
    )

from matplotlib import colormaps

from spectra_inspector.components.bitmap_image import bitmap_image_layout
from spectra_inspector.utilities.coerce import get_sequential_colorscales


def test_bitmap_image_layout():

    _, div_ids = bitmap_image_layout(0)
    for prop in div_ids.prop_names:
        assert prop in getattr(div_ids, prop)
        assert div_ids.get_id_with_index(prop)["index"] == 0


def test_get_sequential_colorscales_restrict_to_common():
    restricted = get_sequential_colorscales(restrict_to_common=True)

    assert restricted
    assert {name.lower() for name in restricted}.issubset(
        {name.lower() for name in colormaps}
    )

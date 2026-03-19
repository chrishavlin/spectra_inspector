from spectra_inspector.components.bitmap_image import bitmap_image_layout


def test_bitmap_image_layout():

    _, div_ids = bitmap_image_layout(0)
    for prop in div_ids.prop_names:
        assert prop in getattr(div_ids, prop)
        assert div_ids.get_id_with_index(prop)["index"] == 0

"""The summary export of a multi-channel panel: the blended image is written
as it is shown (decoded from the figure's PNG), cropped for the box subset,
and described channel by channel in the metadata record and README."""

import numpy as np
import plotly.express as px

from spectra_inspector.tests.test_export_summary import (
    _exported_metadata,
    _written_files,
    _zip_file,
)
from spectra_inspector.utilities.composite import CHANNEL_OFF, compositeChannel

GRAPH_ID = {"type": "bitmap-image-graph", "index": 0}
APPLY_ID = {"type": "composite-image-apply", "index": 0}


def _channel_ids(id_type: str) -> list[dict]:
    return [{"type": id_type, "index": f"0-{c}"} for c in range(3)]


def _composite_figure() -> dict:
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[0, 0] = (255, 0, 0)
    rgb[1, 1] = (0, 255, 0)
    return px.imshow(rgb).to_plotly_json()


def _export(inspector, spectrum_figure, metadata, **kwargs):
    args = {
        "export_clicks": 1,
        "fig_list": [_composite_figure()],
        "shapes_store": {"active_shapes": []},
        "sample_name": "C-12",
        "slider_range_list": [],
        "slider_range_labels": [],
        "spectrum_figure": spectrum_figure,
        "colormaps": [],
        "user_store_dict": {"selected_dataset": "C-12", "spectrum_only": False},
        "export_summary_format": ".zip",
        "active_spectrum_metadata": metadata,
        "msafileformat": "XY",
        "zeroed_elements": [],
        "spectrum_yaxis_scale": "linear",
        "graph_ids": [GRAPH_ID],
        "slider_ids": [],
        "composite_apply_ids": [APPLY_ID],
        "channel_elements": ["Mg", "Al", CHANNEL_OFF],
        "channel_element_ids": _channel_ids("composite-channel-selector-dropdown"),
        "channel_ranges": [[1.13, 1.34], [1.4, 1.61], [1.65, 1.88]],
        "channel_range_ids": _channel_ids("composite-channel-selector-slider"),
        "channel_colors": ["red", "green", "blue"],
        "channel_color_ids": _channel_ids("composite-channel-color"),
        "channel_stretches": [[0, 100], [1, 99], [0, 100]],
        "channel_stretch_ids": _channel_ids("composite-channel-stretch"),
    }
    args.update(kwargs)
    return inspector.export_summary(**args)


def test_composite_zip_writes_the_blend_and_its_subset(
    inspector, spectrum_figure, spectrum_metadata, tmp_path
):
    _export(
        inspector,
        spectrum_figure,
        spectrum_metadata,
        shapes_store={
            "active_shapes": [
                {"type": "rect", "x0": 0.2, "x1": 1.7, "y0": 1.9, "y1": 0.1}
            ]
        },
    )
    written = _written_files(tmp_path)
    assert {
        "bitmap_00_composite_Mg-Al.png",
        "bitmap_00_composite_Mg-Al_subset.png",
    } <= written
    assert not any(name.startswith("bitmap_01") for name in written)

    record = _exported_metadata(tmp_path)
    (image,) = record["images"]
    assert image["file"] == "bitmap_00_composite_Mg-Al.png"
    assert image["subset_file"] == "bitmap_00_composite_Mg-Al_subset.png"
    assert image["element"] is None
    assert image["colormap"] is None
    assert [ch["element"] for ch in image["channels"]] == ["Mg", "Al", None]
    assert [ch["active"] for ch in image["channels"]] == [True, True, False]
    assert image["channels"][1] == {
        "active": True,
        "element": "Al",
        "energy_range_keV": [1.4, 1.61],
        "color": "green",
        "color_hex": "#00ff00",
        "stretch_percentiles": [1.0, 99.0],
    }

    readme = _zip_file(tmp_path).read("README.txt").decode("utf-8")
    assert (
        "bitmap_00_composite_Mg-Al.png: composite of Mg (1.13, 1.34 keV) in red; "
        "Al (1.4, 1.61 keV) in green"
    ) in readme
    assert "bitmap_00_composite_Mg-Al_subset.png: the box region of" in readme


def test_panel_exports_name_single_and_composite_panels(inspector):
    fig = {"data": [], "layout": {}}
    specs = {
        1: [
            compositeChannel("Fe", (6.2, 6.5), "red"),
            compositeChannel("custom", (2.0, 3.0), "green"),
            compositeChannel(CHANNEL_OFF, (0.0, 0.0), "blue"),
        ]
    }
    # by graph index when the ids are known
    panels = inspector._panel_exports(
        [fig, fig],
        [{"type": "bitmap-image-graph", "index": 4}, GRAPH_ID | {"index": 1}],
        [[6.0, 6.5]],
        ["Fe"],
        ["turbo"],
        [{"type": "element-dropdown-slider-slider", "index": 4}],
        specs,
    )
    assert [p.stem for p in panels] == ["bitmap_00_Fe", "bitmap_01_composite_Fe"]
    assert panels[0].colormap == "turbo"
    assert panels[0].energy_range == (6.0, 6.5)
    assert panels[1].composite
    assert panels[1].channels == specs[1]

    # by position without them (the pre-composite export tests)
    panels = inspector._panel_exports(
        [fig, fig], None, [[0.0, 1.0], [2.0, 3.0]], ["none", "Fe"], ["a", "b"], None, {}
    )
    assert [p.stem for p in panels] == ["bitmap_00", "bitmap_01_Fe"]
    assert panels[1].colormap == "b"

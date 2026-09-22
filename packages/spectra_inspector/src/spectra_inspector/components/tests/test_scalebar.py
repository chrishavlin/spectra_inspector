import plotly.express as px
import pytest

from spectra_inspector.components.scalebar import scalebarHandler
from spectra_inspector.utilities.model import CombinedMetadata, EDAX_axis
from spectra_inspector.utilities.scalebar_style import (
    is_scalebar_annotation,
    is_scalebar_trace,
    scalebar_styled,
    scalebarStyle,
)


@pytest.fixture
def md():
    # a 512 x 512 map at ~1.6 um per pixel, keys as strings like the wire format
    axes = {
        "0": EDAX_axis(
            size=512,
            index_in_array=0,
            name="y",
            scale=1.6,
            offset=0,
            units="µm",
            navigate=True,
        ),
        "1": EDAX_axis(
            size=512,
            index_in_array=1,
            name="x",
            scale=1.6,
            offset=0,
            units="µm",
            navigate=True,
        ),
    }
    return CombinedMetadata.model_construct(axes_by_index=axes)


def test_pieces_full_view(md):
    handler = scalebarHandler(width=100, units="um")
    trace, annotation = handler.get_pieces(md)
    # 100 um / 1.6 um per pixel, sitting 1% in from the corner
    assert trace["x"] == [6, 6 + 62]
    assert trace["y"] == [6, 6]
    assert trace["name"] == f"{handler.unyt_width}"
    assert trace["name"].startswith("100")
    assert annotation["y"] == 6
    assert annotation["x"] == 6 + 31


def test_pieces_follow_a_zoom(md):
    handler = scalebarHandler(width=100, units="um")
    trace, annotation = handler.get_pieces(
        md, x_range=[150.2, 306.7], y_range=[138.0, 297.8]
    )
    # ranges are rounded up to whole pixels, then the bar sits 1% in
    assert trace["x"][0] == 151 + 2
    assert trace["y"] == [138 + 2, 138 + 2]
    assert annotation["y"] == 140


def test_pieces_shrink_the_bar_for_a_narrow_view(md):
    handler = scalebarHandler(width=100, units="um")
    trace, _ = handler.get_pieces(md, x_range=[0, 50], y_range=[0, 50])
    assert trace["name"].startswith("10.0")


def test_figure_update_matches_pieces(md):
    handler = scalebarHandler(width=100, units="um")
    fig = px.imshow([[0] * 512] * 512)
    fig.update_xaxes(range=[150.2, 306.7], autorange=False)
    fig.update_yaxes(range=[297.8, 138.0], autorange=False)
    handler.add_to_or_update_figure(fig, md)

    trace, annotation = handler.get_pieces(
        md, x_range=[150.2, 306.7], y_range=[138.0, 297.8]
    )
    assert list(fig.data[1].x) == trace["x"]
    assert list(fig.data[1].y) == trace["y"]
    assert fig.layout.annotations[0].text == annotation["text"]
    assert fig.layout.annotations[0].x == annotation["x"]

    # a second call, after a zoom, updates in place rather than adding a bar
    fig.update_xaxes(range=[0, 50])
    fig.update_yaxes(range=[50, 0])
    handler.add_to_or_update_figure(fig, md)
    assert len(fig.data) == 2
    assert len(fig.layout.annotations) == 1
    assert fig.data[1].name.startswith("10.0")
    assert fig.layout.annotations[0].text.startswith("10.0")


def test_pieces_are_tagged_for_the_export(md):
    trace, annotation = scalebarHandler().get_pieces(md)
    assert is_scalebar_trace(trace)
    assert is_scalebar_annotation(annotation)


def test_scalebar_styled_recolours_or_strips_the_bar_and_label(md):
    fig = px.imshow([[0] * 512] * 512)
    scalebarHandler().add_to_or_update_figure(fig, md)
    figure = fig.to_plotly_json()
    figure["layout"]["shapes"] = [{"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}]

    styled = scalebar_styled(figure, scalebarStyle(color="#ff0000", fontsize=14))
    assert styled["data"][1]["line"]["color"] == "#ff0000"
    assert styled["data"][1]["line"]["width"] == figure["data"][1]["line"]["width"]
    label = styled["layout"]["annotations"][0]
    assert label["font"]["color"] == "#ff0000"
    assert label["font"]["size"] == 14
    assert label["text"] == figure["layout"]["annotations"][0]["text"]
    # everything else is untouched, and so is the browser's figure
    assert styled["layout"]["shapes"] == figure["layout"]["shapes"]
    assert figure["data"][1]["line"]["color"] == "green"

    hidden = scalebar_styled(figure, scalebarStyle(show=False))
    assert len(hidden["data"]) == 1
    assert hidden["layout"]["annotations"] == []
    assert hidden["layout"]["shapes"] == figure["layout"]["shapes"]


def test_scalebar_styled_leaves_a_figure_without_one_alone():
    figure = {
        "data": [{"type": "heatmap"}],
        "layout": {"annotations": [{"text": "other"}]},
    }
    assert scalebar_styled(figure, scalebarStyle(show=False)) == figure
    assert scalebar_styled(figure, scalebarStyle(color="#ff0000")) == figure

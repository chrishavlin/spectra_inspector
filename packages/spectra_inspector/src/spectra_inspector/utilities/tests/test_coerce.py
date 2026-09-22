import numpy as np
import pytest
from matplotlib.colors import to_rgba

from spectra_inspector.utilities.coerce import (
    contrasting_color,
    mpl_color,
    path_vertices,
    placeholder_to_spaces,
    plotly_to_matplotlib,
    spaces_to_placeholder,
)
from spectra_inspector.utilities.matplotib_importer import AnchoredOffsetbox
from spectra_inspector.utilities.selection import (
    END_VERTEX_COLOR,
    POLYGON_COLOR,
    START_VERTEX_COLOR,
    VERTEX_OUTLINE,
    polygon_shapes,
)


def test_spaces_placeholder_roundtrip():
    input_str = " this is a string    with        spaces!"
    assert input_str == placeholder_to_spaces(spaces_to_placeholder(input_str))


def test_plotly_to_matplotlib_preserves_heatmap_box_annotation():
    im_data = [[1, 2], [3, 4]]
    fig = {
        "data": [{"type": "heatmap", "z": im_data}],
        "layout": {"shapes": [{"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}]},
    }

    mpl_fig = plotly_to_matplotlib(fig, im_data=np.asarray(im_data))
    ax = mpl_fig.axes[0]

    assert len(ax.patches) == 1
    assert ax.patches[0].get_edgecolor() == (0.0, 0.0, 0.0, 1.0)
    assert ax.patches[0].get_linewidth() == 2


def test_path_vertices_reads_the_polygon_path():
    assert path_vertices("M 2.0,1.0 L 8.5,1.0 L 5,6e0 Z") == [
        (2.0, 1.0),
        (8.5, 1.0),
        (5.0, 6.0),
    ]
    assert path_vertices("M -1.5,2 L 3,-4") == [(-1.5, 2.0), (3.0, -4.0)]
    assert path_vertices("") == []


def test_mpl_color_passes_names_and_hex_and_converts_rgba():
    assert mpl_color(None, "black") == "black"
    assert mpl_color("", "black") == "black"
    assert mpl_color("#ff0000", "black") == "#ff0000"
    assert mpl_color("white", "black") == "white"
    assert mpl_color("rgb(255, 0, 0)", "black") == (1.0, 0.0, 0.0)
    assert mpl_color("rgba(0, 255, 0, 0.5)", "black") == (0.0, 1.0, 0.0, 0.5)


def test_plotly_to_matplotlib_draws_the_polygon_outline_and_its_corner_dots():
    # the path is drawn unfilled in its own line colour whatever fill it
    # carries; each circle becomes a dot filled with its own colour
    im_data = [[1, 2], [3, 4]]
    points = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
    fig = {
        "data": [{"type": "heatmap", "z": im_data}],
        "layout": {"shapes": polygon_shapes(points, radius=0.25)},
    }

    mpl_fig = plotly_to_matplotlib(fig, im_data=np.asarray(im_data))
    ax = mpl_fig.axes[0]

    outline, *dots = ax.patches
    assert outline.get_closed()
    np.testing.assert_array_equal(outline.get_xy()[:3], points)
    assert outline.get_edgecolor() == to_rgba(POLYGON_COLOR)
    assert not outline.get_fill()

    assert len(dots) == 3
    for dot, (x, y) in zip(dots, points, strict=True):
        assert dot.center == (x, y)
        assert dot.radius == 0.25
        assert dot.get_edgecolor() == to_rgba(VERTEX_OUTLINE)
    assert dots[0].get_facecolor() == to_rgba(START_VERTEX_COLOR)
    assert dots[-1].get_facecolor() == to_rgba(END_VERTEX_COLOR)


def test_plotly_to_matplotlib_uses_the_rectangle_line_colour():
    im_data = [[1, 2], [3, 4]]
    fig = {
        "data": [{"type": "heatmap", "z": im_data}],
        "layout": {
            "shapes": [
                {
                    "type": "rect",
                    "x0": 0,
                    "x1": 1,
                    "y0": 0,
                    "y1": 1,
                    "line": {"color": "#ffffff"},
                }
            ]
        },
    }

    mpl_fig = plotly_to_matplotlib(fig, im_data=np.asarray(im_data))
    (rect,) = mpl_fig.axes[0].patches
    assert rect.get_edgecolor() == (1.0, 1.0, 1.0, 1.0)


def _scalebar_pieces(ax):
    """The bar rectangle and the label text of the export's scalebar box."""
    (box,) = [a for a in ax.artists if isinstance(a, AnchoredOffsetbox)]
    bar, label = box.get_child().get_children()
    (rect,) = bar.get_children()
    (text,) = label.get_children()
    return rect, text


def test_plotly_to_matplotlib_preserves_heatmap_overlay_trace_and_annotation():
    # a figure from before the scalebar carried its tags: the first line
    # trace after the image and the first annotation are the scalebar
    im_data = [[1, 2], [3, 4]]
    fig = {
        "data": [
            {"type": "heatmap", "z": im_data},
            {"type": "scatter", "x": [0, 1], "y": [0, 1]},
        ],
        "layout": {
            "annotations": [{"text": "scale", "x": 0.5, "y": 0.5, "showarrow": False}]
        },
    }

    mpl_fig = plotly_to_matplotlib(fig, im_data=np.asarray(im_data))
    rect, text = _scalebar_pieces(mpl_fig.axes[0])

    assert rect.get_width() == 1
    assert text.get_text() == "scale"


def test_plotly_to_matplotlib_draws_the_scalebar_in_its_own_colour_and_size():
    im_data = np.zeros((512, 512), dtype=int)
    fig = {
        "data": [
            {"type": "heatmap"},
            {
                "type": "scatter",
                "x": [6, 68],
                "y": [6, 6],
                "line": {"color": "#ff0000", "width": 5},
                "meta": {"scalebar": True},
            },
        ],
        "layout": {
            "shapes": [{"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}],
            "annotations": [
                {"text": "other", "x": 0, "y": 0},
                {
                    "name": "scalebar",
                    "text": "100.0 µm",
                    "x": 37,
                    "y": 6,
                    "font": {"color": "#ff0000", "size": 14},
                },
            ],
        },
    }

    mpl_fig = plotly_to_matplotlib(fig, im_data=im_data)
    ax = mpl_fig.axes[0]
    rect, text = _scalebar_pieces(ax)

    # the bar is as many pixels long as the trace spans, in the trace's
    # colour, edged in the contrasting shade; the label matches the
    # annotation, so a red bar carries a red label
    assert rect.get_width() == 62
    assert rect.get_facecolor() == to_rgba("#ff0000")
    assert rect.get_edgecolor() == to_rgba("white")
    assert text.get_text() == "100.0 µm"
    assert text.get_color() == "#ff0000"
    assert text.get_fontsize() == 14
    # the selection is still drawn, and the scalebar is not a line on the axes
    assert len(ax.patches) == 1
    assert len(ax.lines) == 0


def test_plotly_to_matplotlib_draws_no_scalebar_without_a_trace():
    im_data = [[1, 2], [3, 4]]
    fig = {"data": [{"type": "heatmap", "z": im_data}], "layout": {}}

    mpl_fig = plotly_to_matplotlib(fig, im_data=np.asarray(im_data))
    ax = mpl_fig.axes[0]

    assert not [a for a in ax.artists if isinstance(a, AnchoredOffsetbox)]


@pytest.mark.parametrize(
    ("color", "expected"),
    [
        ("#ffffff", "black"),
        ("#000000", "white"),
        ("#ff0000", "white"),
        ("yellow", "black"),
    ],
)
def test_contrasting_color(color, expected):
    assert contrasting_color(color) == expected


def test_plotly_to_matplotlib_carries_log_yaxis_to_spectrum_export():
    fig = {
        "data": [{"type": "scatter", "x": [0, 1, 2], "y": [1, 10, 100]}],
        "layout": {"yaxis": {"type": "log", "title": {"text": "Intensity"}}},
    }

    ax = plotly_to_matplotlib(fig).axes[0]

    assert ax.get_yscale() == "log"
    assert ax.get_xscale() == "linear"
    assert ax.get_ylabel() == "Intensity"


@pytest.mark.parametrize(
    ("layout_type", "override", "expected"),
    [
        ("linear", "log", "log"),
        ("log", "linear", "linear"),
        (None, "log", "log"),
        ("log", None, "log"),
    ],
)
def test_plotly_to_matplotlib_yaxis_scale_overrides_layout(
    layout_type, override, expected
):
    yaxis = {} if layout_type is None else {"type": layout_type}
    fig = {
        "data": [{"type": "scatter", "x": [0, 1, 2], "y": [1, 10, 100]}],
        "layout": {"yaxis": yaxis},
    }

    ax = plotly_to_matplotlib(fig, yaxis_scale=override).axes[0]

    assert ax.get_yscale() == expected


def test_plotly_to_matplotlib_defaults_to_linear_axes():
    fig = {"data": [{"type": "scatter", "x": [0, 1], "y": [1, 2]}], "layout": {}}

    ax = plotly_to_matplotlib(fig).axes[0]

    assert ax.get_yscale() == "linear"

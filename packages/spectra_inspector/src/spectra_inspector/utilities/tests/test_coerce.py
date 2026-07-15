import numpy as np

from spectra_inspector.utilities.coerce import (
    placeholder_to_spaces,
    plotly_to_matplotlib,
    spaces_to_placeholder,
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


def test_plotly_to_matplotlib_preserves_heatmap_overlay_trace_and_annotation():
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
    ax = mpl_fig.axes[0]

    assert len(ax.lines) == 1
    assert ax.texts[0].get_text() == "scale"

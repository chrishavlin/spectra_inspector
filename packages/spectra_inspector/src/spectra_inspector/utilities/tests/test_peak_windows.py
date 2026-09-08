"""The peak integration windows on the spectrum graph (issues #44, #120)."""

import numpy as np
import plotly.graph_objects as go
import pytest

# the inspector page registers itself with the app, so the app must exist first
import spectra_inspector.main  # noqa: F401
from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.utilities import coerce
from spectra_inspector.utilities.peak_windows import (
    FILL_OPACITY,
    LABEL_ROW_OFFSET,
    PALETTE,
    RANGES_KEY,
    apply_peak_windows,
    element_colors,
    integration_ranges,
    is_peak_trace,
    label_rows,
    peak_windows,
    spectrum_element_colors,
    visible_elements,
)

SPECTRUM_GRAPH = "spectrum-container"
SWITCH = "spectrum-peak-windows"

# what the server sends: the windows arrive as JSON arrays, in calibration order
RANGES = {"Si": [1.645, 1.88], "Fe": [6.275, 6.54]}
ENERGY = np.round(np.arange(0.0, 8.0, 0.01), 3).tolist()


@pytest.fixture
def metadata() -> dict:
    # a rising ramp, so the baseline of every window is unambiguous
    return {
        "energy": ENERGY,
        "intensity": [100.0 * e for e in ENERGY],
        "attrs": {
            "weights": {"Si": 0.25, "Fe": 0.5, "total_count": 3},
            RANGES_KEY: RANGES,
        },
    }


def _inside(window):
    e0, e1 = window
    return [e for e in ENERGY if e0 <= e <= e1]


@pytest.mark.parametrize(
    "md",
    [
        None,
        {},
        {"attrs": {}},
        {"attrs": {RANGES_KEY: None}},
        {"attrs": {RANGES_KEY: {}}},
    ],
)
def test_integration_ranges_missing(md):
    assert integration_ranges(md) == {}


def test_integration_ranges(metadata):
    assert integration_ranges(metadata) == {"Si": (1.645, 1.88), "Fe": (6.275, 6.54)}


def test_element_colors_follow_the_order_given():
    colors = element_colors(["Na", "Mg", "Al"])
    assert list(colors) == ["Na", "Mg", "Al"]
    assert list(colors.values()) == list(PALETTE[:3])
    assert len(set(colors.values())) == 3


def test_element_colors_cycle_past_the_palette():
    many = [f"E{i}" for i in range(len(PALETTE) + 2)]
    colors = element_colors(many)
    assert colors[many[-1]] == PALETTE[1]


def test_visible_elements_need_a_window_and_a_weight(metadata):
    assert visible_elements(metadata) == ["Si", "Fe"]
    # a zero weight (nothing found in the DH assessment) hides the peak
    metadata["attrs"]["weights"]["Si"] = 0.0
    assert visible_elements(metadata) == ["Fe"]
    # so does zeroing the element out in the table; a reset brings it back
    assert visible_elements(metadata, ["Fe"]) == []
    assert visible_elements(metadata, []) == ["Fe"]
    # no weights at all (an uncalibrated spectrum) means no peaks
    metadata["attrs"]["weights"] = None
    assert visible_elements(metadata) == []


def test_peak_windows(metadata):
    windows = peak_windows(metadata)
    colors = spectrum_element_colors(metadata)

    assert [t["name"] for t in windows.traces] == ["Si", "Fe"]
    assert [s["name"] for s in windows.shapes] == ["Si", "Fe"]
    assert [a["text"] for a in windows.annotations] == ["Si", "Fe"]

    for trace, line, label in zip(
        windows.traces, windows.shapes, windows.annotations, strict=True
    ):
        element = trace["name"]
        e0, e1 = RANGES[element]
        center = (e0 + e1) / 2
        # the vertical line sits at the centre of the window and the label on it
        assert line["type"] == "line"
        assert line["x0"] == line["x1"] == center
        assert label["x"] == center
        assert label["xanchor"] == "center"
        # colour coded to match the weights table
        assert trace["fillcolor"] == colors[element]
        assert line["line"]["color"] == colors[element]
        assert label["font"]["color"] == colors[element]
        assert trace["opacity"] == FILL_OPACITY
        # the lines and labels are anchored to the paper so they span the plot
        # on any y scale; the fill follows the data
        for item in (line, label):
            assert item["yref"] == "paper"
            assert item["xref"] == "x"
        assert is_peak_trace(trace)
        assert trace["showlegend"] is False
        assert trace["fill"] == "toself"


def test_fill_runs_from_the_curve_to_the_window_baseline(metadata):
    (si, _) = peak_windows(metadata).traces
    xs = _inside(RANGES["Si"])
    n = len(xs)
    assert n > 2
    # out along the curve, back along the baseline
    assert si["x"][:n] == xs
    assert si["x"][n:] == xs[::-1]
    curve = [100.0 * e for e in xs]
    assert si["y"][:n] == curve
    baseline = (curve[0] + curve[-1]) / 2
    assert si["y"][n:] == [baseline] * n
    assert si["meta"]["baseline"] == baseline
    # each window has its own baseline
    (_, fe) = peak_windows(metadata).traces
    assert fe["meta"]["baseline"] != baseline


def test_no_fill_without_samples_in_the_window(metadata):
    # the window still gets its line and label, only the area cannot be drawn
    metadata["energy"] = [0.0, 4.0, 8.0]
    metadata["intensity"] = [1.0, 2.0, 3.0]
    windows = peak_windows(metadata)
    assert windows.traces == []
    assert [s["name"] for s in windows.shapes] == ["Si", "Fe"]


def test_zeroed_elements_lose_their_peak(metadata):
    windows = peak_windows(metadata, True, ["Si"])
    assert [t["name"] for t in windows.traces] == ["Fe"]
    assert [s["name"] for s in windows.shapes] == ["Fe"]
    assert [a["text"] for a in windows.annotations] == ["Fe"]
    # hiding a peak does not shift the colours of the others
    assert windows.traces[0]["fillcolor"] == spectrum_element_colors(metadata)["Fe"]


def test_labels_of_neighbouring_windows_alternate_rows():
    # the server's Na/Mg/Al/Si/P windows are ~0.25 keV apart: every other
    # label moves up a row; K and Ca are far enough apart to share row 0
    ranges = {
        "Na": [0.96, 1.12],
        "Mg": [1.13, 1.34],
        "Al": [1.40, 1.61],
        "Si": [1.645, 1.88],
        "P": [1.905, 2.10],
        "K": [3.235, 3.47],
        "Ca": [3.57, 3.84],
        "Fe": [6.275, 6.54],
    }
    centers = {el: (e0 + e1) / 2 for el, (e0, e1) in ranges.items()}
    assert label_rows(centers) == {
        "Na": 0,
        "Mg": 1,
        "Al": 0,
        "Si": 1,
        "P": 0,
        "K": 0,
        "Ca": 0,
        "Fe": 0,
    }

    md = {"attrs": {RANGES_KEY: ranges, "weights": dict.fromkeys(ranges, 1.0)}}
    windows = peak_windows(md)
    y_by_label = {a["text"]: a["y"] for a in windows.annotations}
    assert y_by_label["Na"] == 1
    assert y_by_label["Mg"] == 1 + LABEL_ROW_OFFSET
    assert y_by_label["Fe"] == 1
    assert {a["yanchor"] for a in windows.annotations} == {"bottom"}


def test_hidden_peaks_skip_a_row_they_no_longer_crowd():
    # with Mg zeroed out, Al is far enough from Na to sit on row 0 again
    ranges = {"Na": [0.96, 1.12], "Mg": [1.13, 1.34], "Al": [1.40, 1.61]}
    md = {"attrs": {RANGES_KEY: ranges, "weights": dict.fromkeys(ranges, 1.0)}}
    rows = {a["text"]: a["y"] for a in peak_windows(md, True, ["Mg"]).annotations}
    assert rows == {"Na": 1, "Al": 1}


@pytest.mark.parametrize("show", [False, None])
def test_peak_windows_hidden(metadata, show):
    windows = peak_windows(metadata, show)
    assert (windows.traces, windows.shapes, windows.annotations) == ([], [], [])


def test_peak_windows_without_ranges():
    md = {"attrs": {"weights": {"Si": 0.25}}}
    windows = peak_windows(md, True)
    assert (windows.traces, windows.shapes, windows.annotations) == ([], [], [])
    assert spectrum_element_colors(md) == {}


def test_apply_peak_windows(metadata):
    fig = go.Figure(go.Scatter(x=[0.0, 8.0], y=[1.0, 2.0])).to_plotly_json()
    fig["layout"]["yaxis"] = {"type": "log"}

    shown = apply_peak_windows(fig, metadata, True)
    assert [t.get("name") for t in shown["data"]] == [None, "Si", "Fe"]
    assert {s["name"] for s in shown["layout"]["shapes"]} == {"Si", "Fe"}
    assert shown["layout"]["yaxis"] == {"type": "log"}
    # the page's figure is left alone
    assert len(fig["data"]) == 1
    assert "shapes" not in fig["layout"]

    # re-applying replaces the peak traces instead of stacking them
    again = apply_peak_windows(shown, metadata, True, ["Si"])
    assert [t.get("name") for t in again["data"]] == [None, "Fe"]

    hidden = apply_peak_windows(shown, metadata, False)
    assert len(hidden["data"]) == 1
    assert hidden["layout"]["shapes"] == []
    assert hidden["layout"]["annotations"] == []
    assert apply_peak_windows(None, metadata, True) is None


def test_new_spectrum_figure_draws_the_peaks(metadata):
    from spectra_inspector.pages.inspector import new_spectrum_figure

    fig = new_spectrum_figure(
        metadata["energy"], metadata["intensity"], "log", metadata, True
    )
    assert [t.name for t in fig.data] == ["Full energy range", "Si", "Fe"]
    assert [s.name for s in fig.layout.shapes] == ["Si", "Fe"]
    assert [a.text for a in fig.layout.annotations] == ["Si", "Fe"]
    assert fig.layout.yaxis.type == "log"

    fig = new_spectrum_figure(
        metadata["energy"], metadata["intensity"], "log", metadata, True, ["Fe"]
    )
    assert [t.name for t in fig.data] == ["Full energy range", "Si"]

    fig = new_spectrum_figure(
        metadata["energy"], metadata["intensity"], "log", metadata, False
    )
    assert len(fig.data) == 1
    assert len(fig.layout.shapes) == 0
    assert len(fig.layout.annotations) == 0


def test_matplotlib_export_carries_the_peaks(metadata):
    from spectra_inspector.pages.inspector import new_spectrum_figure

    fig = new_spectrum_figure(
        metadata["energy"], metadata["intensity"], "linear", metadata, True
    )
    mpl_fig = coerce.plotly_to_matplotlib(fig.to_plotly_json())
    ax = mpl_fig.axes[0]
    colors = spectrum_element_colors(metadata)

    # one filled area per element, the curve plus one centre line per element,
    # and no legend for the fills
    assert len(ax.patches) == 2
    assert len(ax.lines) == 1 + 2
    assert ax.get_legend() is None
    assert [t.get_text() for t in ax.texts] == ["Si", "Fe"]
    si_center = (RANGES["Si"][0] + RANGES["Si"][1]) / 2
    assert ax.texts[0].get_position()[0] == si_center
    assert ax.texts[0].get_color() == colors["Si"]
    assert ax.lines[1].get_xdata()[0] == si_center
    assert ax.patches[0].get_alpha() == FILL_OPACITY
    coerce.plt.close(mpl_fig)


def test_matplotlib_export_leaves_data_shapes_alone():
    # a rectangle anchored to data on y (an image panel's box) is not a peak
    fig = go.Figure(go.Scatter(x=[0.0, 8.0], y=[1.0, 2.0], mode="lines"))
    fig.add_shape(type="rect", x0=1, x1=2, y0=1, y1=2)

    mpl_fig = coerce.plotly_to_matplotlib(fig.to_plotly_json())
    assert len(mpl_fig.axes[0].patches) == 0
    coerce.plt.close(mpl_fig)


@pytest.fixture
def callbacks(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app._callback_list


def _dep_ids(deps: list[dict]) -> set[str]:
    return {str(dep.get("id")) for dep in deps}


def test_switch_and_zeroed_elements_redraw_the_peaks_without_refetching(callbacks):
    toggles = [cb for cb in callbacks if SWITCH in _dep_ids(cb["inputs"])]
    assert len(toggles) == 1
    (toggle,) = toggles
    assert SPECTRUM_GRAPH in toggle["output"]
    assert "zeroed-elements" in _dep_ids(toggle["inputs"])
    assert "active-spectrum-metadata" in _dep_ids(toggle["state"])
    assert "full-spectrum-store" not in _dep_ids(toggle["state"])


def test_spectrum_creation_and_export_read_the_switch(callbacks):
    builders = [
        cb
        for cb in callbacks
        if "active-shapes" in _dep_ids(cb["inputs"]) and SPECTRUM_GRAPH in cb["output"]
    ]
    assert len(builders) == 1
    assert SWITCH in _dep_ids(builders[0]["state"])
    assert "zeroed-elements" in _dep_ids(builders[0]["state"])

    exporters = [
        cb
        for cb in callbacks
        if any("data-export-panel" in str(dep.get("id")) for dep in cb["inputs"])
        and SPECTRUM_GRAPH in _dep_ids(cb["state"])
    ]
    assert len(exporters) == 1
    assert SWITCH in _dep_ids(exporters[0]["state"])
    assert "zeroed-elements" in _dep_ids(exporters[0]["state"])


def _find(component, target_id):
    if getattr(component, "id", None) == target_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, list):
        children = [children]
    for child in children:
        found = _find(child, target_id)
        if found is not None:
            return found
    return None


def test_switch_defaults_to_shown():
    from spectra_inspector.pages.inspector import _IDS, layout

    switch = _find(layout(sample_name=None), _IDS.spectrum_peak_windows)

    assert switch is not None
    assert switch.value is True

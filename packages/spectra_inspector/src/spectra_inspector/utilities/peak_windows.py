"""The peak integration windows drawn over the spectrum graph (issues #44, #120).

The server sends the energy window it summed for each element's weight along
with the weights themselves. Here each window becomes the area between the
curve and a per-window baseline (the mean of the curve's first and last value
inside the window), a dotted vertical line through the centre of the window
and the element label sitting on that line. A window is only drawn while its
element has a non-zero weight, so an element the DH assessment found nothing
for -- or one the user has zeroed out in the weights table -- has no peak. The
colours are shared with the weights table so a row can be matched to its peak
at a glance.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

import plotly.express as px
from dash import html

RANGES_KEY = "integration_ranges_keV"
FILL_OPACITY = 0.4
LABEL_FONT_SIZE = 11
# labels whose centres are closer than this (keV) alternate between two rows so
# the Na/Mg/Al/Si/P cluster stays legible, in the browser and in the export
MIN_LABEL_SEPARATION_KEV = 0.3
LABEL_ROW_OFFSET = 0.07
# marks the fill traces so they can be told apart from the spectrum itself
TRACE_META_KEY = "peak_window"

# a categorical palette that reads on both the light and the dark theme
PALETTE: tuple[str, ...] = tuple(px.colors.qualitative.D3)


@dataclass
class peakWindows:
    """What drawing the windows adds to a figure: one fill trace per peak
    (``data``) and the centre lines and labels (``layout``)."""

    traces: list[dict] = field(default_factory=list)
    shapes: list[dict] = field(default_factory=list)
    annotations: list[dict] = field(default_factory=list)


def element_colors(elements: Iterable[str]) -> dict[str, str]:
    """One palette colour per element, assigned in the order given."""
    return {el: PALETTE[i % len(PALETTE)] for i, el in enumerate(elements)}


def integration_ranges(
    active_spectrum_metadata: dict | None,
) -> dict[str, tuple[float, float]]:
    """The per-element integration windows of a spectrum, empty when the server
    could not calibrate it (and so sent no weights either)."""
    attrs = (active_spectrum_metadata or {}).get("attrs") or {}
    ranges = attrs.get(RANGES_KEY) or {}
    return {el: (float(rng[0]), float(rng[1])) for el, rng in ranges.items()}


def spectrum_element_colors(active_spectrum_metadata: dict | None) -> dict[str, str]:
    """The colour of every element that has a window on this spectrum, keyed
    the same way for the graph and for the weights table. Colours follow the
    server's order and do not shift when a peak is hidden."""
    return element_colors(integration_ranges(active_spectrum_metadata))


def visible_elements(
    active_spectrum_metadata: dict | None, zeroed_elements: Iterable[str] = ()
) -> list[str]:
    """The elements whose peak is drawn: those with a window and a weight that
    is still above zero once the user's zeroed-out elements are applied."""
    attrs = (active_spectrum_metadata or {}).get("attrs") or {}
    weights = attrs.get("weights") or {}
    zeroed = set(zeroed_elements)
    return [
        el
        for el in integration_ranges(active_spectrum_metadata)
        if el not in zeroed and (weights.get(el) or 0) > 0
    ]


def element_swatch(color: str, muted: bool = False) -> html.Span:
    """The colour chip the weights table shows next to an element's name; muted
    when that element's peak is not drawn."""
    return html.Span(
        title="peak not drawn" if muted else None,
        style={
            "display": "inline-block",
            "width": "0.7rem",
            "height": "0.7rem",
            "marginRight": "0.5rem",
            "borderRadius": "2px",
            "backgroundColor": color,
            "opacity": 0.25 if muted else 1,
            "verticalAlign": "middle",
        },
    )


def label_rows(centers: dict[str, float]) -> dict[str, int]:
    """Which of two rows each label sits on: a label goes up to row 1 when it
    would otherwise crowd the previous label on row 0."""
    rows: dict[str, int] = {}
    last_on_row: dict[int, float | None] = {0: None, 1: None}
    for element, center in sorted(centers.items(), key=lambda item: item[1]):
        row = 0
        previous = last_on_row[0]
        if previous is not None and center - previous < MIN_LABEL_SEPARATION_KEV:
            row = 1
        rows[element] = row
        last_on_row[row] = center
    return rows


def _fill_trace(
    element: str,
    window: tuple[float, float],
    energy: list[float],
    intensity: list[float],
    color: str,
) -> dict | None:
    """The closed polygon between the curve and the window's baseline, or None
    when fewer than two samples fall inside the window."""
    e0, e1 = window
    inside = [(e, i) for e, i in zip(energy, intensity, strict=True) if e0 <= e <= e1]
    if len(inside) < 2:
        return None
    xs = [e for e, _ in inside]
    ys = [i for _, i in inside]
    baseline = (ys[0] + ys[-1]) / 2.0
    return {
        "type": "scatter",
        "mode": "lines",
        "x": [*xs, *reversed(xs)],
        "y": [*ys, *([baseline] * len(xs))],
        "fill": "toself",
        "fillcolor": color,
        "opacity": FILL_OPACITY,
        "line": {"width": 0, "color": color},
        "hoverinfo": "skip",
        "showlegend": False,
        "name": element,
        "meta": {TRACE_META_KEY: element, "baseline": baseline},
    }


def is_peak_trace(trace: dict) -> bool:
    meta = trace.get("meta")
    return isinstance(meta, dict) and TRACE_META_KEY in meta


def peak_windows(
    active_spectrum_metadata: dict | None,
    show: bool | None = True,
    zeroed_elements: Iterable[str] = (),
) -> peakWindows:
    """Everything that draws the visible peaks of a spectrum.

    The lines and labels are anchored to the paper on the y axis so they span
    the full height whatever the y scale (linear or log) or zoom; the fills
    follow the curve itself. Empty when the windows are switched off or the
    spectrum has none, so applying the result also clears a previous set.
    """
    result = peakWindows()
    if not show:
        return result

    ranges = integration_ranges(active_spectrum_metadata)
    colors = element_colors(ranges)
    visible = visible_elements(active_spectrum_metadata, zeroed_elements)
    centers = {el: (ranges[el][0] + ranges[el][1]) / 2.0 for el in visible}
    rows = label_rows(centers)
    md = active_spectrum_metadata or {}
    energy = md.get("energy") or []
    intensity = md.get("intensity") or []
    for element in visible:
        color = colors[element]
        center = centers[element]
        trace = _fill_trace(element, ranges[element], energy, intensity, color)
        if trace is not None:
            result.traces.append(trace)
        result.shapes.append(
            {
                "type": "line",
                "name": element,
                "xref": "x",
                "yref": "paper",
                "x0": center,
                "x1": center,
                "y0": 0,
                "y1": 1,
                "line": {"color": color, "width": 1, "dash": "dot"},
                "layer": "below",
            }
        )
        result.annotations.append(
            {
                "name": element,
                "text": element,
                "x": center,
                "y": 1 + rows[element] * LABEL_ROW_OFFSET,
                "xref": "x",
                "yref": "paper",
                "xanchor": "center",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"color": color, "size": LABEL_FONT_SIZE},
            }
        )
    return result


def apply_peak_windows(
    figure: dict | None,
    active_spectrum_metadata: dict | None,
    show: bool | None = True,
    zeroed_elements: Iterable[str] = (),
) -> dict | None:
    """A copy of a figure dict with its peaks redrawn (or cleared) to match
    ``show``, the spectrum's windows and the zeroed-out elements. Any peak
    traces already on the figure are replaced; the spectrum trace is kept."""
    if figure is None:
        return None
    windows = peak_windows(active_spectrum_metadata, show, zeroed_elements)
    kept = [t for t in figure.get("data") or [] if not is_peak_trace(t)]
    return {
        **figure,
        "data": [*kept, *windows.traces],
        "layout": {
            **(figure.get("layout") or {}),
            "shapes": windows.shapes,
            "annotations": windows.annotations,
            # plotly would otherwise show a legend as soon as a second trace
            # exists, even one that opts out of it
            "showlegend": False,
        },
    }

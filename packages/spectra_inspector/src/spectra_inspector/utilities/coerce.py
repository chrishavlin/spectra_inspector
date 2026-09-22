import base64
import io
import re

import numpy as np
import numpy.typing as npt
import plotly.express as px
import plotly.graph_objects as go
from matplotlib import colormaps
from PIL import Image

from spectra_inspector.logging import spectraLogger
from spectra_inspector.utilities.matplotib_importer import (
    AnchoredOffsetbox,
    AuxTransformBox,
    Circle,
    FontProperties,
    Polygon,
    Rectangle,
    TextArea,
    VPacker,
    to_rgb,
    withStroke,
)
from spectra_inspector.utilities.matplotib_importer import mpl_pyplot as plt
from spectra_inspector.utilities.scalebar_style import (
    is_scalebar_annotation,
    is_scalebar_trace,
)

_PATH_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def path_vertices(path: str) -> list[tuple[float, float]]:
    """The ``(x, y)`` points of a plotly path shape made of straight
    segments (``M x,y L x,y ... Z``), as the polygon selection draws them."""
    numbers = [float(n) for n in _PATH_NUMBER.findall(path)]
    return list(zip(numbers[0::2], numbers[1::2], strict=False))


_RGBA = re.compile(r"rgba?\(\s*([^)]*)\)")


def mpl_color(color: str | None, default: str) -> str | tuple[float, ...]:
    """A plotly colour as matplotlib takes it: names and hex pass through,
    ``rgb(...)`` / ``rgba(...)`` become fractions, nothing gives ``default``."""
    if not color:
        return default
    match = _RGBA.fullmatch(color.strip())
    if match is None:
        return color
    parts = [float(p) for p in match.group(1).split(",")]
    rgb = tuple(p / 255.0 for p in parts[:3])
    return (*rgb, parts[3]) if len(parts) > 3 else rgb


_place_holder = "___"

_PLOTLY_DASHES = {"solid": "-", "dash": "--", "dot": ":", "dashdot": "-."}
_PLOTLY_HALIGN = {"left": "left", "center": "center", "right": "right"}
_PLOTLY_VALIGN = {"top": "top", "middle": "center", "bottom": "bottom"}

_mpl_cmaps_lower = {name.lower(): name for name in colormaps}


def get_sequential_colorscales(restrict_to_common: bool = True) -> list[str]:
    all_colors = px.colors.named_colorscales()
    seq_attrs = [
        att.lower() for att in dir(px.colors.sequential) if not att.startswith("_")
    ]

    plotly_colormaps = [clr for clr in all_colors if clr.lower() in seq_attrs]

    if restrict_to_common:
        plotly_colormaps = [
            clr for clr in plotly_colormaps if clr.lower() in _mpl_cmaps_lower
        ]

    plotly_colormaps.sort()
    return plotly_colormaps


def spaces_to_placeholder(input: str) -> str:
    return input.replace(" ", _place_holder)


def placeholder_to_spaces(input: str) -> str:
    return input.replace(_place_holder, " ")


def plotly_im_trace_to_array(trace_data: dict) -> npt.NDArray:
    im_data = trace_data["z"]
    shp = [int(dim) for dim in im_data["shape"].replace(" ", "").split(",")]
    data = im_data["_inputArray"]
    im_array = np.zeros(shp, dtype=np.int64)
    for irow in range(shp[0]):
        data_i = data[irow]
        im_array[irow, :] = list(data_i.values())

    return im_array


def plotly_image_trace_to_array(trace_data: dict) -> npt.NDArray:
    """The pixels of an ``image`` trace as a ``(rows, cols, 3)`` uint8 array.

    ``px.imshow`` ships an RGB image as a base64 PNG data URI in ``source``,
    which the browser hands back untouched; an explicit ``z`` array (a figure
    built with ``binary_string=False``) is accepted too.
    """
    source = trace_data.get("source")
    if isinstance(source, str) and source.startswith("data:image"):
        encoded = source.split(",", maxsplit=1)[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as im:
            return np.asarray(im.convert("RGB"), dtype=np.uint8)
    z = trace_data.get("z")
    if z is None:
        msg = "image trace carries neither a source nor a z array"
        raise ValueError(msg)
    return np.asarray(z, dtype=np.uint8)


def _draw_paper_spanning_shapes(ax, layout: dict) -> None:
    """Re-draw the shapes and labels that span the full plot height.

    These are the spectrum's peak integration windows (``utilities/peak_windows``):
    rectangles become ``axvspan``, lines ``axvline`` and the labels sit at the
    same paper-relative height via the x-axis transform. Shapes anchored to
    data on the y axis are not carried over.
    """
    for shape in layout.get("shapes", []) or []:
        if shape.get("yref") != "paper":
            continue
        x0 = shape.get("x0")
        x1 = shape.get("x1")
        if x0 is None or x1 is None:
            continue
        if shape.get("type") == "rect":
            ax.axvspan(
                x0,
                x1,
                facecolor=shape.get("fillcolor", "gray"),
                alpha=shape.get("opacity", 1.0),
                linewidth=0,
                zorder=0,
            )
        elif shape.get("type") == "line":
            line = shape.get("line") or {}
            ax.axvline(
                x0,
                color=line.get("color", "black"),
                linewidth=line.get("width", 1),
                linestyle=_PLOTLY_DASHES.get(line.get("dash", "solid"), "-"),
                zorder=0,
            )

    for annotation in layout.get("annotations", []) or []:
        if annotation.get("yref") != "paper" or annotation.get("xref") != "x":
            continue
        text = annotation.get("text")
        x = annotation.get("x")
        if not isinstance(text, str) or x is None:
            continue
        font = annotation.get("font") or {}
        ax.text(
            x,
            annotation.get("y", 1.0),
            text,
            transform=ax.get_xaxis_transform(),
            ha=_PLOTLY_HALIGN.get(annotation.get("xanchor"), "center"),
            va=_PLOTLY_VALIGN.get(annotation.get("yanchor"), "bottom"),
            color=font.get("color", "black"),
            fontsize=font.get("size", 10),
        )


def _find_scalebar_trace(data: list[dict]) -> dict | None:
    """The scalebar's line trace: the one tagged as such, else the first line
    trace after the image (how figures were built before the tag)."""
    tagged = next((trace for trace in data if is_scalebar_trace(trace)), None)
    if tagged is not None:
        return tagged
    return next(
        (trace for trace in data[1:] if trace.get("type") in {"scatter", "line"}),
        None,
    )


def _find_scalebar_annotation(annotations: list[dict]) -> dict | None:
    tagged = next((a for a in annotations if is_scalebar_annotation(a)), None)
    if tagged is not None:
        return tagged
    return annotations[0] if annotations else None


# the bar's thickness as a fraction of the image's height, so it comes out
# the same on the page whatever the map's pixel count
SCALEBAR_HEIGHT_FRACTION = 0.012


def contrasting_color(color) -> str:
    """Black or white, whichever stands out against ``color``."""
    r, g, b = to_rgb(color)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "black" if luminance > 0.5 else "white"


def _draw_scalebar(
    ax, trace: dict, annotation: dict | None, n_rows: int
) -> AnchoredOffsetbox | None:
    """Draw the scalebar as an anchored box in the image's upper-left corner:
    the bar (its length in pixels from the trace) with the label centred
    below it and a gap between the two, both in the trace's colour and the
    label at the annotation's font size, edged in black or white so they read
    on any colormap."""
    x = trace.get("x", [])
    if len(x) < 2:
        return None
    length = float(np.max(x) - np.min(x))
    if length <= 0:
        return None

    color = mpl_color((trace.get("line") or {}).get("color"), "white")
    font = (annotation or {}).get("font") or {}
    fontsize = float(font.get("size") or 10)
    edge = contrasting_color(color)

    bar = AuxTransformBox(ax.transData)
    bar.add_artist(
        Rectangle(
            (0, 0),
            length,
            SCALEBAR_HEIGHT_FRACTION * n_rows,
            facecolor=color,
            edgecolor=edge,
            linewidth=0.6,
        )
    )
    children = [bar]
    text = (annotation or {}).get("text")
    if isinstance(text, str) and text:
        children.append(
            TextArea(
                text,
                textprops={
                    "color": mpl_color(font.get("color"), color),
                    "fontsize": fontsize,
                    "path_effects": [withStroke(linewidth=1.5, foreground=edge)],
                },
            )
        )
    box = AnchoredOffsetbox(
        loc="upper left",
        child=VPacker(children=children, align="center", pad=0, sep=0.35 * fontsize),
        pad=0,
        borderpad=0.8,
        frameon=False,
        prop=FontProperties(size=fontsize),
    )
    ax.add_artist(box)
    return box


def plotly_to_matplotlib(
    fig: dict | go.Figure | None,
    im_data: npt.NDArray | None = None,
    cmap: str | None = None,
    include_colorbar: bool = False,
    yaxis_scale: str | None = None,
):
    """Convert a Plotly figure into a Matplotlib figure for static exports.

    The conversion preserves the underlying data values and carries over common
    styling cues such as axis titles, visible axes, and line styling. When
    ``yaxis_scale`` is given ("linear" or "log") it overrides the y-axis type
    recorded in the figure's layout.
    """
    if fig is None:
        return None

    if isinstance(fig, go.Figure):
        fig_dict = fig.to_plotly_json()
    else:
        fig_dict = fig

    data = fig_dict.get("data", [])
    if not data:
        return None

    layout = fig_dict.get("layout", {})
    xaxis = layout.get("xaxis", {})
    yaxis = layout.get("yaxis", {})
    title = layout.get("title", {})

    first_trace = data[0]
    trace_type = first_trace.get("type", "scatter")
    if trace_type in {"heatmap", "image"}:
        if im_data is not None:
            z = im_data
        elif trace_type == "heatmap":
            z = plotly_im_trace_to_array(first_trace)
        else:
            z = plotly_image_trace_to_array(first_trace)
        spectraLogger.info(f"extracted data {z.shape}, {z.dtype}")
        fig_mpl, ax = plt.subplots(figsize=(6, 4), dpi=150)

        # an RGB image carries its own colours; a scalar map takes the colormap
        if z.ndim == 3:
            cmap_name = None
        else:
            cmap_name = cmap if isinstance(cmap, str) else "viridis"
            if cmap_name in _mpl_cmaps_lower:
                cmap_name = _mpl_cmaps_lower[cmap_name]

        im = ax.imshow(z, cmap=cmap_name)
        ax.set_aspect("equal", adjustable="box")

        # add on the selection: the box, or the polygon's outline (a path)
        # and its corner dots (circles), in the shapes' own colours; the
        # outline is never filled
        for shape in layout.get("shapes", []) or []:
            line_color = mpl_color((shape.get("line") or {}).get("color"), "black")
            kind = shape.get("type")
            if kind == "path":
                corners = path_vertices(shape.get("path", ""))
                if len(corners) >= 2:
                    ax.add_patch(
                        Polygon(
                            corners,
                            closed=len(corners) >= 3,
                            fill=False,
                            edgecolor=line_color,
                            linewidth=2,
                        )
                    )
                continue
            if kind not in {"rect", "circle"}:
                continue

            x0 = shape.get("x0")
            x1 = shape.get("x1")
            y0 = shape.get("y0")
            y1 = shape.get("y1")
            if None in {x0, x1, y0, y1}:
                continue

            if kind == "circle":
                ax.add_patch(
                    Circle(
                        ((x0 + x1) / 2, (y0 + y1) / 2),
                        abs(x1 - x0) / 2,
                        facecolor=mpl_color(shape.get("fillcolor"), line_color),
                        edgecolor=line_color,
                        linewidth=1,
                    )
                )
                continue

            rect = Rectangle(
                (x0, y0),
                x1 - x0,
                y1 - y0,
                fill=False,
                edgecolor=line_color,
                linewidth=2,
            )
            ax.add_patch(rect)

        scalebar_trace = _find_scalebar_trace(data)
        if scalebar_trace is not None:
            _draw_scalebar(
                ax,
                scalebar_trace,
                _find_scalebar_annotation(layout.get("annotations", []) or []),
                n_rows=z.shape[0],
            )

        ax.set_axis_off()
        if include_colorbar and z.ndim == 2:
            fig_mpl.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

        title_text = title.get("text") if isinstance(title, dict) else None
        if title_text:
            ax.set_title(title_text, pad=8)
        return fig_mpl

    fig_mpl, ax = plt.subplots(figsize=(6, 4), dpi=150)
    labelled = 0
    for trace in data:
        trace_type = trace.get("type", "scatter")
        if trace_type in {"scatter", "line"} and trace.get("fill") == "toself":
            # a filled polygon (the spectrum's peak areas), never in the legend
            ax.fill(
                trace.get("x", []),
                trace.get("y", []),
                facecolor=trace.get("fillcolor", "gray"),
                alpha=trace.get("opacity", 1.0),
                linewidth=0,
                zorder=1,
            )
        elif trace_type in {"scatter", "line"}:
            x = trace.get("x", [])
            y = trace.get("y", [])
            labelled += 1
            line_kwargs = {}
            if trace.get("line") and isinstance(trace["line"], dict):
                line_style = trace["line"].get("dash")
                if line_style:
                    line_kwargs["linestyle"] = _PLOTLY_DASHES.get(
                        line_style, line_style
                    )
                color = trace["line"].get("color")
                if color:
                    line_kwargs["color"] = color
            ax.plot(x, y, label=trace.get("name"), **line_kwargs)
            ax.set_xlim(left=0, right=8)

    _draw_paper_spanning_shapes(ax, layout)

    if isinstance(xaxis, dict):
        title_text = xaxis.get("title", {}).get("text")
        if title_text:
            ax.set_xlabel(title_text)
        if xaxis.get("visible") is False:
            ax.set_xlabel("")
            ax.set_xticks([])
            ax.set_xticklabels([])
        if xaxis.get("type") == "log":
            ax.set_xscale("log")
    if isinstance(yaxis, dict):
        title_text = yaxis.get("title", {}).get("text")
        if title_text:
            ax.set_ylabel(title_text)
        if yaxis.get("visible") is False:
            ax.set_ylabel("")
            ax.set_yticks([])
            ax.set_yticklabels([])
        if yaxis_scale is None:
            yaxis_scale = yaxis.get("type")
    if yaxis_scale == "log":
        ax.set_yscale("log")
    if isinstance(title, dict):
        title_text = title.get("text")
        if title_text:
            ax.set_title(title_text, pad=8)

    if labelled > 1:
        ax.legend(loc="best")
    return fig_mpl

import numpy as np
import numpy.typing as npt
import plotly.express as px
import plotly.graph_objects as go
from matplotlib import colormaps

from spectra_inspector.logging import spectraLogger
from spectra_inspector.utilities.matplotib_importer import Rectangle
from spectra_inspector.utilities.matplotib_importer import mpl_pyplot as plt

_place_holder = "___"

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


def plotly_to_matplotlib(
    fig: dict | go.Figure | None,
    im_data: npt.NDArray | None = None,
    cmap: str | None = None,
    include_colorbar: bool = False,
):
    """Convert a Plotly figure into a Matplotlib figure for static exports.

    The conversion preserves the underlying data values and carries over common
    styling cues such as axis titles, visible axes, and line styling.
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
    if trace_type == "heatmap":
        if im_data is None:
            z = plotly_im_trace_to_array(first_trace)
        else:
            z = im_data
        spectraLogger.info(f"extracted data {z.shape}, {z.dtype}")
        fig_mpl, ax = plt.subplots(figsize=(6, 4), dpi=150)

        # handle colormap coercion
        if isinstance(cmap, str):
            cmap_name = cmap
        else:
            cmap_name = "viridis"
        if cmap_name in _mpl_cmaps_lower:
            cmap_name = _mpl_cmaps_lower[cmap_name]

        im = ax.imshow(z, cmap=cmap_name)
        ax.set_aspect("equal", adjustable="box")

        # add on box annotations
        for shape in layout.get("shapes", []) or []:
            if shape.get("type") != "rect":
                continue

            x0 = shape.get("x0")
            x1 = shape.get("x1")
            y0 = shape.get("y0")
            y1 = shape.get("y1")
            if None in {x0, x1, y0, y1}:
                continue

            rect = Rectangle(
                (x0, y0),
                x1 - x0,
                y1 - y0,
                fill=False,
                edgecolor="black",
                linewidth=2,
            )
            ax.add_patch(rect)

        # scale bar
        if len(data) > 1:
            scalebar_trace = next(
                (
                    trace
                    for trace in data[1:]
                    if trace.get("type") in {"scatter", "line"}
                ),
                None,
            )
            if scalebar_trace is not None:
                x = scalebar_trace.get("x", [])
                if len(x) >= 2:
                    start_x = 0.0

                    xmin = np.min(x)
                    xmax = np.max(x)
                    start_x = 0
                    end_x = xmax - xmin
                    bar_y = float(im.get_extent()[3]) if im is not None else 0.0
                    ax.plot(
                        [start_x, end_x],
                        [bar_y, bar_y],
                        color="black",
                        linewidth=1.5,
                    )

                    bar_center = (start_x + end_x) / 2.0
                    text_y = bar_y  # - 0.08 * max(1.0, xmax-xmin)

                    annotations = layout.get("annotations", []) or []
                    if annotations:
                        annotation = annotations[0]
                        text = annotation.get("text")
                        if isinstance(text, str):
                            ax.text(
                                bar_center,
                                text_y,
                                text,
                                color="black",
                                fontsize=10,
                                ha="center",
                                va="top",
                            )

        ax.set_axis_off()
        if include_colorbar:
            fig_mpl.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

        title_text = title.get("text") if isinstance(title, dict) else None
        if title_text:
            ax.set_title(title_text, pad=8)
        return fig_mpl

    fig_mpl, ax = plt.subplots(figsize=(6, 4), dpi=150)
    for trace in data:
        trace_type = trace.get("type", "scatter")
        if trace_type in {"scatter", "line"}:
            x = trace.get("x", [])
            y = trace.get("y", [])
            line_kwargs = {}
            if trace.get("line") and isinstance(trace["line"], dict):
                line_style = trace["line"].get("dash")
                if line_style:
                    line_kwargs["linestyle"] = {
                        "solid": "-",
                        "dash": "--",
                        "dot": ":",
                        "dashdot": "-.",
                    }.get(line_style, line_style)
                color = trace["line"].get("color")
                if color:
                    line_kwargs["color"] = color
            ax.plot(x, y, label=trace.get("name"), **line_kwargs)
            ax.set_xlim(left=0, right=8)

    if isinstance(xaxis, dict):
        title_text = xaxis.get("title", {}).get("text")
        if title_text:
            ax.set_xlabel(title_text)
        if xaxis.get("visible") is False:
            ax.set_xlabel("")
            ax.set_xticks([])
            ax.set_xticklabels([])
    if isinstance(yaxis, dict):
        title_text = yaxis.get("title", {}).get("text")
        if title_text:
            ax.set_ylabel(title_text)
        if yaxis.get("visible") is False:
            ax.set_ylabel("")
            ax.set_yticks([])
            ax.set_yticklabels([])
    if isinstance(title, dict):
        title_text = title.get("text")
        if title_text:
            ax.set_title(title_text, pad=8)

    if len(data) > 1:
        ax.legend(loc="best")
    return fig_mpl

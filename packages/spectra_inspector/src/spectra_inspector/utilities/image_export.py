"""Write an image panel's export figure without resampling its pixels.

``coerce.plotly_to_matplotlib`` draws an image panel as a matplotlib figure:
the map through ``imshow``, with the selection outline, the scalebar and the
title on top. Saving that figure resamples the map to the figure's size, and
matplotlib does so through several float copies of it, which costs gigabytes
for a large map whatever size comes out.

So the map and its annotations are rendered apart and put back together:

- the map's pixels are coloured here, a block of rows at a time, through the
  figure's own colormap and normalisation, after being averaged down by the
  export's scale factor (1 keeps every pixel);
- the image is taken out of the figure and what is left (outline, scalebar,
  title) is drawn on a transparent canvas of exactly the map's pixel size,
  with the axes filling it, so a data coordinate lands on its own pixel;
- Pillow composites the two.

The title sits in a strip above the map rather than over it, so the written
image is that much taller than the size ``export_image_size`` reports.
"""

import math

import numpy as np
import numpy.typing as npt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from PIL import Image

# resolution of the figures that are saved whole (the spectrum plot)
FIGURE_DPI = 200

# a map smaller than this on its longer side is enlarged by a whole factor,
# each pixel becoming a block, so the annotations have pixels to be drawn
# with. Low enough that reducing an ordinary map is not undone by it.
MIN_IMAGE_SIDE = 256

# the longer side the PDF and the deck are given: what a page or a slide can
# show, so those documents stay a sensible size
PAGE_IMAGE_SIDE = 1600

# the title strip's height in units of the title's font size
_TITLE_STRIP = 2.0
_COLOR_BLOCK_ROWS = 256


def page_scale_factor(shape: tuple[int, int]) -> int:
    """The smallest scale factor that fits a map of ``shape`` (rows, columns)
    on a page."""
    return max(1, math.ceil(max(shape) / PAGE_IMAGE_SIDE))


def _enlargement(rows: int, cols: int) -> int:
    return max(1, math.ceil(MIN_IMAGE_SIDE / max(rows, cols)))


def export_image_size(shape: tuple[int, int], factor: int) -> tuple[int, int]:
    """The (rows, columns) a map of ``shape`` is written with at ``factor``,
    title strip aside."""
    rows = math.ceil(shape[0] / factor)
    cols = math.ceil(shape[1] / factor)
    enlarge = _enlargement(rows, cols)
    return rows * enlarge, cols * enlarge


def image_axes(fig: Figure) -> Axes | None:
    """The axes of a figure that is one image and its annotations, None for
    anything else (a line plot, an image with a colorbar beside it)."""
    if len(fig.axes) != 1 or len(fig.axes[0].images) != 1:
        return None
    return fig.axes[0]


def reduce_image(image: npt.NDArray, factor: int) -> npt.NDArray:
    """``image`` averaged over ``factor`` x ``factor`` blocks of pixels. Blocks
    cut short by the right and bottom edges average the pixels they have."""
    if factor == 1:
        return image
    rows, cols = image.shape[:2]
    pad = [(0, -rows % factor), (0, -cols % factor)] + [(0, 0)] * (image.ndim - 2)
    if pad[0][1] or pad[1][1]:
        image = np.pad(image, pad, mode="edge")
    blocks = image.reshape(
        image.shape[0] // factor, factor, image.shape[1] // factor, factor, -1
    )
    reduced = blocks.mean(axis=(1, 3))
    if image.ndim == 2:
        return reduced[..., 0]
    return np.rint(reduced).astype(image.dtype)


def _colored(ax: Axes, factor: int) -> Image.Image:
    """The axes' image as RGBA pixels, reduced by ``factor``. A scalar map
    goes through the image's colormap and normalisation; the limits were set
    from the full map, so a reduced image keeps the full one's colours."""
    mappable = ax.images[0]
    data = reduce_image(np.ma.getdata(mappable.get_array()), factor)
    rows, cols = data.shape[:2]
    rgba = np.empty((rows, cols, 4), dtype=np.uint8)
    for start in range(0, rows, _COLOR_BLOCK_ROWS):
        block = slice(start, start + _COLOR_BLOCK_ROWS)
        rgba[block] = mappable.to_rgba(data[block], bytes=True)
    return Image.fromarray(rgba)


def _overlay(
    fig: Figure, ax: Axes, size: tuple[int, int], extent: tuple[int, int]
) -> tuple[Image.Image, int]:
    """Everything the figure draws but its image, on a transparent canvas
    ``size`` (rows, columns) plus a title strip, whose height is returned too.
    ``extent`` is the (rows, columns) of map the canvas spans, in the map's
    own pixels, which is what the annotations are placed in."""
    rows, cols = size
    # how large the image is drawn in the figure as it stands: scaling to the
    # canvas by that keeps every label and line the size it has there,
    # relative to the image
    ax.apply_aspect()
    position = ax.get_position()
    dpi = cols / (position.width * fig.get_figwidth())

    title = ax.get_title()
    title_size = ax.title.get_fontsize()
    strip = math.ceil(_TITLE_STRIP * title_size * dpi / 72) if title else 0
    height = rows + strip

    ax.images[0].remove()
    ax.set_title("")
    fig.set_dpi(dpi)
    # the canvas is sized by truncation, so a hair over the whole pixel count
    fig.set_size_inches((cols + 1e-6) / dpi, (height + 1e-6) / dpi)
    fig.patch.set_alpha(0.0)
    ax.set_aspect("auto")
    ax.set_position((0.0, 0.0, 1.0, rows / height))
    ax.set_xlim(-0.5, extent[1] - 0.5)
    ax.set_ylim(extent[0] - 0.5, -0.5)

    if title:
        text = fig.text(
            0.5,
            1 - strip / (2 * height),
            title,
            ha="center",
            va="center",
            fontsize=title_size,
        )
        width = text.get_window_extent(fig.canvas.get_renderer()).width
        if width > 0.96 * cols:
            text.set_fontsize(title_size * 0.96 * cols / width)

    fig.canvas.draw()
    canvas = np.array(fig.canvas.buffer_rgba())
    if canvas.shape[:2] != (height, cols):
        msg = (
            f"the annotations were drawn on {canvas.shape[1]}x{canvas.shape[0]} "
            f"pixels, the image has {cols}x{height}"
        )
        raise RuntimeError(msg)
    return Image.fromarray(canvas), strip


def render_image_figure(fig: Figure, factor: int = 1) -> Image.Image:
    """The image figure ``fig`` (see ``image_axes``) as a picture holding its
    map at one pixel per ``factor`` x ``factor`` map pixels, annotated as the
    figure is. ``fig`` is taken apart in the process."""
    ax = image_axes(fig)
    if ax is None:
        msg = "not a figure of a single image"
        raise ValueError(msg)
    shape = ax.images[0].get_array().shape[:2]

    image = _colored(ax, factor)
    reduced = (image.height, image.width)
    enlarge = _enlargement(*reduced)
    if enlarge > 1:
        image = image.resize(
            (image.width * enlarge, image.height * enlarge), Image.Resampling.NEAREST
        )

    overlay, strip = _overlay(
        fig,
        ax,
        (image.height, image.width),
        (reduced[0] * factor, reduced[1] * factor),
    )
    assert (image.height, image.width) == export_image_size(shape, factor)

    out = Image.new("RGBA", overlay.size, "white")
    out.paste(image, (0, strip))
    out.alpha_composite(overlay)
    return out.convert("RGB")

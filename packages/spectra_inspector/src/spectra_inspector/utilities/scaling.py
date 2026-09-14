import numpy as np

from spectra_inspector.utilities.model import CombinedMetadata, EDAX_axis


def get_axis(md: CombinedMetadata, index: int) -> EDAX_axis:
    """Look up an axis by its position in the array.

    `axes_by_index` is keyed by int on the server but crosses the wire as a JSON
    object, so its keys arrive -- and are typed in the generated models -- as
    strings.
    """
    return md.axes_by_index[str(index)]


def get_closest_index(ax: EDAX_axis, value: float) -> int:
    dx = ax.scale
    min_val = ax.offset
    return int(np.round((value - min_val) / dx))


def get_image_shape(md: CombinedMetadata) -> tuple[int, int]:
    """The map's (rows, columns), which is the shape of every image panel.

    Found through the spatial axes' names, as the scalebar does, falling back to
    array order (index 0 is the rows) when the names are anything else.
    """
    by_name = {ax.name: ax for ax in md.axes_by_index.values()}
    if "y" in by_name and "x" in by_name:
        return by_name["y"].size, by_name["x"].size
    return get_axis(md, 0).size, get_axis(md, 1).size

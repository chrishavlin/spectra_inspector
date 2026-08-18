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

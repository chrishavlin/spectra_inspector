import numpy as np

from spectra_inspector.server.model import EDAX_axis


def get_closest_index(ax: EDAX_axis, value: float) -> int:
    dx = ax.scale
    min_val = ax.offset
    return int(np.round((value - min_val) / dx))

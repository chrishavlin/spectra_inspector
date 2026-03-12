from spectra_inspector.utilities.model import EDAX_axis
import numpy as np 


def get_closest_index(ax: EDAX_axis, value: float | int) -> int:
    dx = ax.scale
    min_val = ax.offset    
    return int(np.round((value - min_val)/dx))
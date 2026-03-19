import numpy as np
import numpy.typing as npt

_place_holder = "___"


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

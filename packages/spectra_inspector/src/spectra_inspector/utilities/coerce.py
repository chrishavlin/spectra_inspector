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


def sync_layouts(layout_update: dict, fig_list: list):

    new_fig_list = []
    for fig in fig_list:
        if fig is not None and "layout" in fig:
            fig["layout"].update(layout_update)
        new_fig_list.append(fig)
    return new_fig_list


def copy_layout_attrs(fig_list: list, ref_fig, layout_attrs: list[str] | None = None):
    if layout_attrs is None:
        layout_attrs = ["xaxis", "yaxis", "shapes", "annotations"]
    layout_update = {}
    for attr in layout_attrs:
        if isinstance(ref_fig, dict) and "layout" in ref_fig:
            attrval = ref_fig["layout"].get(attr, None)
            if attrval:
                layout_update[attr] = attrval
    return sync_layouts(layout_update, fig_list)


def copy_layout_attrs_for_new_fig(
    fig_list: list, new_index_loc: int, layout_attrs: list[str] | None = None
):
    if len(fig_list) > 1:
        if new_index_loc == 0:
            ref_index = 1
        else:
            ref_index = 0
        ref_fig = fig_list[ref_index]
        return copy_layout_attrs(fig_list, ref_fig, layout_attrs=layout_attrs)
    return fig_list

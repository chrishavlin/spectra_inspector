from dataclasses import dataclass
from typing import Any

import numpy as np
from plotly.graph_objects import Figure
from unyt import unyt_quantity

from spectra_inspector.utilities.model import CombinedMetadata, EDAX_axis


def get_pixel_scalebar(ax: EDAX_axis, scalebar_length: unyt_quantity) -> int:
    """get the number of pixels for a given length

    Parameters
    ----------
    ax : EDAX_axis
        _description_
    scalebar_length : float
        _description_

    Returns
    -------
    int
        _description_
    """
    dx = unyt_quantity(ax.scale, ax.units)
    n_pixels = scalebar_length / dx
    return int(np.round(n_pixels.value))


@dataclass
class scalebarHandler:
    width: float = 100
    units: str = "um"
    pixel_height: int = 5
    pixel_offset_x: float = 1
    pixel_offset_y: float = 5
    color: str = "green"
    auto_rescale: bool = True

    @property
    def unyt_width(self) -> unyt_quantity:
        uq = unyt_quantity(self.width, self.units)
        assert isinstance(uq, unyt_quantity)
        return uq

    def get_trace(
        self,
        md: CombinedMetadata,
        plot_origin_x: float = 0,
        plot_origin_y: float = 0,
        override_width: unyt_quantity | None = None,
    ) -> dict[str, Any]:

        if override_width is not None:
            width_ = override_width
        else:
            width_ = self.unyt_width
        scalebar_wid_pixels = get_pixel_scalebar(md.axes_by_index[0], width_)

        x0 = plot_origin_x + self.pixel_offset_x
        y0 = plot_origin_y + self.pixel_offset_y
        new_trace = {
            "mode": "lines",
            "x": [x0, x0 + scalebar_wid_pixels],
            "y": [y0, y0],
            "type": "scatter",
            "name": f"{width_.value} {width_.units}",
            "line": {"width": self.pixel_height, "color": self.color},
        }

        return new_trace

    def add_to_or_update_figure(
        self,
        fig: Figure | None,
        md: CombinedMetadata,
    ):

        if fig is None:
            return

        plot_origin = [0.0, 0.0]
        widths: list[float | None] = [None, None]
        for iax, ax in enumerate(["x", "y"]):
            rng = conditionally_get_axis_range(fig, ax)
            if rng is not None and rng[0] > 0:
                widths[iax] = rng[1] - rng[0]
                plot_origin[iax] = rng[0]

        override_width = self.unyt_width
        if widths[0] is not None:
            xwidth = unyt_quantity(widths[0], self.units)
            if xwidth < self.unyt_width:
                xlog = np.log10(xwidth)
                override_width = unyt_quantity(10 ** np.floor(xlog), self.units)

        new_trace = self.get_trace(
            md,
            plot_origin_x=plot_origin[0],
            plot_origin_y=plot_origin[1],
            override_width=override_width,
        )

        figdata = fig["data"]
        if figdata is None:
            return

        if len(figdata) <= 1:
            # no scalebar yet, add it
            fig.add_trace(new_trace)
        else:
            fig["data"][1] = new_trace


def conditionally_get_axis_range(
    fig: Figure | None, ax: str
) -> None | tuple[float, float]:
    if fig is None:
        return None

    try:
        rng_raw = fig["layout"][f"{ax}axis"]["range"]
        if rng_raw is None:
            return None
        rng = np.sort(np.asarray(fig["layout"][f"{ax}axis"]["range"]))
        return rng[0], rng[1]
    except KeyError:
        pass
    return None

from dataclasses import dataclass
from typing import Any

import numpy as np
from plotly.graph_objects import Figure
from unyt import unyt_quantity

from spectra_inspector.utilities.model import CombinedMetadata, EDAX_axis
from spectra_inspector.utilities.scaling import get_axis


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
    pixel_offset_factor: float = 0.01
    pixel_offset_initial: int = 5
    color: str = "green"
    fontsize: int = 12
    auto_rescale: bool = True

    @property
    def unyt_width(self) -> unyt_quantity:
        uq = unyt_quantity(self.width, self.units)
        assert isinstance(uq, unyt_quantity)
        return uq

    def get_trace(
        self,
        md: CombinedMetadata,
        x0: float = 0.0,
        y0: float = 0.0,
        override_width: unyt_quantity | None = None,
    ) -> dict[str, Any]:

        if override_width is not None:
            width_ = override_width
        else:
            width_ = self.unyt_width
        scalebar_wid_pixels = get_pixel_scalebar(get_axis(md, 0), width_)

        new_trace = {
            "mode": "lines",
            "x": [x0, x0 + scalebar_wid_pixels],
            "y": [y0, y0],
            "type": "scatter",
            "name": f"{width_.value} {width_.units}",
            "line": {"width": self.pixel_height, "color": self.color},
        }

        return new_trace

    def get_pieces(
        self,
        md: CombinedMetadata,
        x_range: list[float] | None = None,
        y_range: list[float] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """The scalebar trace and its label annotation for a view.

        Ranges are ascending pixel ranges of the visible image; None means the
        full axis. The bar shrinks to a round number when the view is narrower
        than the default width.
        """
        widths = {"x": 0.0, "y": 0.0}
        scalebar_pos = {"x": 0.0, "y": 0.0}
        ax_to_id = {ax.name: iax for iax, ax in md.axes_by_index.items()}
        for ax, requested in (("x", x_range), ("y", y_range)):
            low, high = (
                requested
                if requested is not None
                else (0, md.axes_by_index[ax_to_id[ax]].size)
            )
            rng = np.ceil([max(low, 0), high])

            widths[ax] = rng[1] - rng[0]
            scalebar_pos[ax] = rng[0] + np.ceil(self.pixel_offset_factor * widths[ax])

        xwidth = unyt_quantity(widths["x"], self.units)
        override_width = self.unyt_width
        if xwidth < self.unyt_width:
            xlog = np.log10(xwidth)
            override_width = unyt_quantity(10 ** np.floor(xlog), self.units)

        scalebar_wid_pixels = get_pixel_scalebar(get_axis(md, 0), override_width)
        text_x_loc = scalebar_pos["x"] + scalebar_wid_pixels / 2

        new_trace = self.get_trace(
            md,
            x0=scalebar_pos["x"],
            y0=scalebar_pos["y"],
            override_width=override_width,
        )

        text_annotate_dict = {
            "x": text_x_loc,
            "y": scalebar_pos["y"],
            "text": f"{override_width}",
            "showarrow": False,
            "yshift": -10,
            "font": {
                "size": self.fontsize,
                "color": self.color,
                "weight": 1000,
            },
        }
        return new_trace, text_annotate_dict

    def add_to_or_update_figure(
        self,
        fig: Figure | None,
        md: CombinedMetadata,
    ):

        if fig is None:
            return

        figdata = fig["data"]
        if figdata is None:
            return

        new_trace, text_annotate_dict = self.get_pieces(
            md,
            x_range=conditionally_get_axis_range(fig, "x"),
            y_range=conditionally_get_axis_range(fig, "y"),
        )

        if len(figdata) <= 1:
            # no scalebar yet, add it
            fig.add_trace(new_trace)
            fig.add_annotation(**text_annotate_dict)
        else:
            fig.data[1].update({k: v for k, v in new_trace.items() if k != "type"})
            fig.layout.annotations[0].update(text_annotate_dict)


def conditionally_get_axis_range(fig: Figure | None, ax: str) -> None | list[float]:
    if fig is None:
        return None

    try:
        rng_raw = fig["layout"][f"{ax}axis"]["range"]
        if rng_raw is None:
            return None
        rng = np.sort(np.asarray(fig["layout"][f"{ax}axis"]["range"]))
        return rng.tolist()
    except KeyError:
        pass
    return None

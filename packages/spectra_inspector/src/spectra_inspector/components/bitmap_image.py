from concurrent.futures import ThreadPoolExecutor

import dash_bootstrap_components as dbc
import numpy as np
import numpy.typing as npt
import plotly.express as px
from dash import Patch, dcc, html
from dash_bootstrap_components import Button
from plotly.colors import get_colorscale

from spectra_inspector.components.energy_range_slider import (
    build_element_dropdown_and_slider,
)
from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.components.scalebar import scalebarHandler
from spectra_inspector.logging import spectraLogger
from spectra_inspector.settings import Settings
from spectra_inspector.user_store_model import UserStore
from spectra_inspector.utilities.coerce import get_sequential_colorscales
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import CombinedMetadata
from spectra_inspector.utilities.scaling import get_axis, get_closest_index
from spectra_inspector.utilities.view_sync import apply_view_to_figure

_colorscales = get_sequential_colorscales()


class bitmapImageLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "graph",
        "refresh",
        "delete",
        "colorscale",
        "loadingoverlay",
    )

    def __init__(
        self, id_type_base: str = "bitmap-image", index: int | None = None
    ) -> None:
        super().__init__(id_type_base, index)

    @property
    def graph(self) -> str:
        return self.full_id("-graph")

    @property
    def refresh(self) -> str:
        return self.full_id("-refresh")

    @property
    def delete(self) -> str:
        return self.full_id("-delete")

    @property
    def colorscale(self) -> str:
        return self.full_id("-colorscale")

    @property
    def loadingoverlay(self) -> str:
        return self.full_id("-loadingoverlay")


def graph_style(im_shape: tuple[int, ...] | None = None) -> dict[str, str]:
    """The graph's container style: full panel width, height following the
    image's aspect ratio so a wider panel gets a taller image rather than a
    letterboxed one. Square until the image shape is known."""
    nrows, ncols = (im_shape[0], im_shape[1]) if im_shape is not None else (1, 1)
    return {"width": "100%", "aspectRatio": f"{ncols} / {nrows}"}


def bitmap_image_layout(
    index: int,
    id_type_base: str = "bitmap-image",
    delete_button_label: str = "X",
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
    init_element: str | None = None,
    colorscale: str = "turbo",
) -> tuple[dbc.Card, bitmapImageLayoutIDs]:

    imIDs = bitmapImageLayoutIDs(id_type_base=id_type_base, index=index)

    fig_image = dcc.Loading(
        dcc.Graph(
            id=imIDs.get_id_with_index("graph"),
            config={
                "modeBarButtonsToAdd": [
                    # "drawclosedpath",
                    # "drawcircle",
                    "drawrect",
                    "eraseshape",
                ],
                "modeBarButtonsToRemove": ["resetScale", "autoScale"],
                "displayModeBar": True,
                "displaylogo": False,
            },
            responsive=True,
            style=graph_style(),
        ),
        id=imIDs.loadingoverlay,
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        type="circle",
        # the overlay swallows mouse events while shown, so only show it for
        # updates that take a while (fetching an image) and not for the quick
        # layout patches that keep the panels in sync.
        delay_show=300,
        delay_hide=250,
    )

    energy_parts, _ = build_element_dropdown_and_slider(
        index=index,
        slider_start=slider_start,
        slider_stop=slider_stop,
        slider_step=slider_step,
        init_element=init_element,
    )

    delete_button = Button(
        delete_button_label,
        id=imIDs.get_id_with_index("delete"),
        color="secondary",
    )

    # element pick, Apply and delete share the header so the image starts as
    # high up the panel as possible; the buttons right-align off ms-auto.
    header = dbc.CardHeader(
        dbc.Row(
            [
                dbc.Col(energy_parts.dropdown, width="auto"),
                dbc.Col(energy_parts.apply_button, width="auto", className="ms-auto"),
                dbc.Col(delete_button, width="auto"),
            ],
            align="center",
            className="g-2",
        ),
        className="px-2 py-2",
    )

    colormap_dropdown = dcc.Dropdown(
        id=imIDs.get_id_with_index("colorscale"),
        options=_colorscales,
        value=colorscale,
        searchable=False,
        placeholder=colorscale,
        className="text-info",
    )

    _controls_row = dbc.Row(
        [
            dbc.Col(energy_parts.collapse_button, width="auto"),
            dbc.Col(html.Span("Colormap:"), width="auto", className="ms-auto"),
            dbc.Col(colormap_dropdown, style={"minWidth": "7rem"}),
        ],
        align="center",
        className="g-2 mb-2",
    )

    _primary_graph_div = dbc.Card(
        [
            header,
            dbc.CardBody(
                [
                    _controls_row,
                    energy_parts.collapse,
                    fig_image,
                    *energy_parts.tooltips,
                    dbc.Tooltip(
                        "Delete bitmap image panel",
                        target=imIDs.get_id_with_index("delete"),
                    ),
                    dbc.Tooltip(
                        "Apply changes to energy bounds",
                        target=imIDs.get_id_with_index("refresh"),
                    ),
                ],
                className="p-2",
            ),
        ],
        id=imIDs.get_id_with_index("div"),
    )

    return _primary_graph_div, imIDs


def fetch_im_data(
    user_store: UserStore,
    slider_range: tuple[float, float],
    md: CombinedMetadata,
) -> npt.NDArray:
    """Fetch one summed image over the slider's energy range.

    Split out of get_new_im so several panels can be fetched at once -- this is
    the only blocking call in building a figure, and it dominates everything
    else by three orders of magnitude.
    """
    channel_axis = get_axis(md, 2)
    indx0 = get_closest_index(channel_axis, slider_range[0])
    indx1 = get_closest_index(channel_axis, slider_range[1])

    msg = f"fetching image data: {user_store.selected_dataset}, {indx0}, {indx1}"
    spectraLogger.info(msg)
    sisi = SpectraInspectorServerInterface()
    im = sisi.image_data_summed(
        user_store.selected_dataset,
        (indx0, indx1),
        directory_sync=user_store.directory_sync(),
    )
    return np.array(im.image).reshape(im.shape)


def fetch_im_data_parallel(
    user_store: UserStore,
    slider_ranges: list[tuple[float, float]],
    md: CombinedMetadata,
) -> list[npt.NDArray]:
    """Fetch several panels' image data concurrently, in slider_ranges order.

    requests releases the GIL while waiting on the socket, so threads are
    enough here: the work is all on the backend, which serves the requests in
    parallel when it runs with more than one worker.

    Concurrent requests necessarily land on different workers, so in desktop
    mode each one carries the working directory out of the user store (see
    UserStore.directory_sync) and any worker that missed the original
    selection rescans before answering.
    """
    max_parallel = Settings().max_parallel_image_fetches
    if len(slider_ranges) == 1 or max_parallel <= 1:
        return [fetch_im_data(user_store, rng, md) for rng in slider_ranges]

    workers = min(len(slider_ranges), max_parallel)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda rng: fetch_im_data(user_store, rng, md),
                slider_ranges,
            )
        )


def get_new_im(
    user_store: UserStore,
    slider_range: tuple[float, float],
    color_scale: str,
    im_data: npt.NDArray | None = None,
    scalebar_handler: scalebarHandler | None = None,
    zmin: float | None = None,
    zmax: float | None = None,
    md: CombinedMetadata | None = None,
    view: dict | None = None,
    shapes: list[dict] | None = None,
):

    if md is None:
        md = user_store.conditionally_fetch_metadata()
    assert md is not None

    if im_data is None:
        im_data = fetch_im_data(user_store, slider_range, md)

    fig = px.imshow(
        im_data,
        color_continuous_scale=color_scale,
        # height=im_height,
        zmin=zmin,
        zmax=zmax,
    )
    fig.update_layout(
        coloraxis_showscale=False,
        margin_b=5,
        margin_l=5,
        margin_r=5,
        margin_t=5,
        autosize=True,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(dragmode="drawrect")
    # px.imshow keeps the aspect ratio with constrain="domain". plotly.js resolves
    # that constraint against a private record of the last range set by a user
    # interaction, so a zoom set on the figure from python (the other panels)
    # comes out a few pixels different from the zoom dragged out in the browser.
    # constrain="range" depends on the current range alone and lands every panel
    # on the same view.
    fig.update_xaxes(constrain="range")
    fig.update_yaxes(constrain="range")

    # the shared view must be in place before the scalebar is sized to it
    apply_view_to_figure(fig, view, shapes)

    if scalebar_handler is not None:
        scalebar_handler.add_to_or_update_figure(fig, md)

    return fig


def colorscale_patch(color_scale: str) -> Patch:
    """A figure patch swapping the colormap of an image built by ``get_new_im``.

    px.imshow puts the scale on the layout's ``coloraxis``, so a layout patch is
    all it takes and the image data never leaves the browser.
    """
    patch = Patch()
    patch["layout"]["coloraxis"]["colorscale"] = get_colorscale(color_scale)
    return patch

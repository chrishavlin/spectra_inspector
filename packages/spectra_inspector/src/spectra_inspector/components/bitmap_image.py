import dash_bootstrap_components as dbc
import numpy as np
import numpy.typing as npt
import plotly.express as px
from dash import dcc, html
from dash_bootstrap_components import Button

from spectra_inspector.components.energy_range_slider import (
    get_element_dropdown_and_slider,
)
from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.components.scalebar import scalebarHandler
from spectra_inspector.logging import spectraLogger
from spectra_inspector.user_store_model import UserStore
from spectra_inspector.utilities.coerce import get_sequential_colorscales
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.scaling import get_closest_index

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


def bitmap_image_layout(
    index: int,
    id_type_base: str = "bitmap-image",
    delete_button_label: str = "X",
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
    init_element_id: int = 0,
    colorscale: str = "reds",
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
        ),
        id=imIDs.loadingoverlay,
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        type="circle",
        delay_hide=2000,
    )

    energy_range_selector, _ = get_element_dropdown_and_slider(
        index=index,
        slider_start=slider_start,
        slider_stop=slider_stop,
        slider_step=slider_step,
        init_element_id=init_element_id,
    )

    _controls_row_1 = dbc.Row(
        [
            dbc.Col(energy_range_selector, width=12),
        ],
        align="center",
    )

    colormap_dropdown = dcc.Dropdown(
        id=imIDs.get_id_with_index("colorscale"),
        options=_colorscales,
        value=colorscale,
        searchable=False,
        placeholder=colorscale,
        className="text-info",
    )

    _controls_row_2 = dbc.Row(
        [
            dbc.Col(dcc.Markdown("Colormap:"), width=4),
            dbc.Col(colormap_dropdown, width=8),
        ],
        align="center",
    )

    _controls_row_3 = dbc.Row(
        [
            dbc.Col(
                Button(
                    delete_button_label,
                    id=imIDs.get_id_with_index("delete"),
                    color="secondary",
                ),
                width=1,
            ),
            dbc.Col([], width=11),
        ],
        class_name="g-0",
    )

    _primary_graph_div = dbc.Card(
        dbc.CardBody(
            [
                html.Hr(),
                _controls_row_1,
                html.Hr(),
                _controls_row_2,
                html.Hr(),
                dbc.Row(dbc.Col(fig_image), align="center"),
                _controls_row_3,
                dbc.Tooltip(
                    "Delete bitmap image panel",
                    target=imIDs.get_id_with_index("delete"),
                ),
                dbc.Tooltip(
                    "Apply changes to energy bounds",
                    target=imIDs.get_id_with_index("refresh"),
                ),
            ]
        ),
        id=imIDs.get_id_with_index("div"),
        # color="primary",
        # inverse=True,
    )

    return _primary_graph_div, imIDs


def get_new_im(
    user_store: UserStore,
    slider_range: tuple[float, float],
    color_scale: str,
    im_data: npt.NDArray | None = None,
    scalebar_handler: scalebarHandler | None = None,
    zmin: float | None = None,
    zmax: float | None = None,
):

    sisi = SpectraInspectorServerInterface()
    md = user_store.conditionally_fetch_metadata()
    assert md is not None

    if im_data is None:
        indx0 = get_closest_index(md.axes_by_index[2], slider_range[0])
        indx1 = get_closest_index(md.axes_by_index[2], slider_range[1])

        msg = f"fetching image data: {user_store.selected_dataset}, {indx0}, {indx1}"
        spectraLogger.info(msg)
        im = sisi.image_data_summed(user_store.selected_dataset, (indx0, indx1))
        im_data = np.array(im.image).reshape(im.shape)

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

    if scalebar_handler is not None:
        scalebar_handler.add_to_or_update_figure(fig, md)

    return fig

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
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.scaling import get_closest_index


def _get_sequential_colorscales() -> list[str]:
    _all_colors = px.colors.named_colorscales()
    seq_attrs = [
        att.lower() for att in dir(px.colors.sequential) if not att.startswith("_")
    ]

    colornames = [clr for clr in _all_colors if clr.lower() in seq_attrs]
    colornames.sort()
    return colornames


_colorscales = _get_sequential_colorscales()


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
    bg_hexcolor: str = "#FFFFFF",
    button_label: str = "Apply Bounds",
    delete_button_label: str = "Delete Image",
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
    init_element_id: int = 0,
    colorscale: str = "blackbody",
) -> tuple[html.Div, bitmapImageLayoutIDs]:

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

    colormap_dropdown = dcc.Dropdown(
        id=imIDs.get_id_with_index("colorscale"),
        options=_colorscales,
        value=colorscale,
        searchable=False,
        placeholder=colorscale,
        style={"color": "#000000"},
    )

    _controls_row_2 = dbc.Row(
        [
            dbc.Col(Button(button_label, id=imIDs.get_id_with_index("refresh"))),
            dbc.Col(
                Button(
                    delete_button_label,
                    id=imIDs.get_id_with_index("delete"),
                ),
            ),
            dbc.Col(colormap_dropdown),
        ],
        align="center",
    )

    _primary_graph_div = html.Div(
        [
            energy_range_selector,
            _controls_row_2,
            dbc.Row(dbc.Col(fig_image), align="center"),
        ],
        id=imIDs.get_id_with_index("div"),
        style={
            "padding": "5px",
            "backgroundColor": bg_hexcolor,
            "min-height": "600px",
            # "border": "2px black solid",
        },
    )

    return _primary_graph_div, imIDs


def get_new_im(
    user_store: UserStore,
    slider_range: tuple[float, float],
    color_scale: str,
    im_data: npt.NDArray | None = None,
    im_height: int = 600,
    scalebar_handler: scalebarHandler | None = None,
):

    sisi = SpectraInspectorServerInterface()
    md = user_store.conditionally_fetch_metadata()
    assert md is not None
    indx0 = get_closest_index(md.axes_by_index[2], slider_range[0])
    indx1 = get_closest_index(md.axes_by_index[2], slider_range[1])
    msg = f"fetching image data: {user_store.selected_dataset}, {indx0}, {indx1}"
    spectraLogger.info(msg)

    if im_data is None:
        im = sisi.image_data_summed(user_store.selected_dataset, (indx0, indx1))
        im_data = np.array(im.image).reshape(im.shape)

    fig = px.imshow(im_data, color_continuous_scale=color_scale, height=im_height)
    fig.update_layout(
        coloraxis_showscale=False,
        margin_b=0,
        margin_l=0,
        margin_r=0,
        margin_t=50,
        autosize=True,
        # pad=0
    )
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showticklabels=False)

    if scalebar_handler is not None:
        scalebar_handler.add_to_or_update_figure(fig, md)

    return fig

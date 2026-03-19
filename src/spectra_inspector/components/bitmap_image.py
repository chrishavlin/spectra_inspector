from dash import dcc, html
from dash_bootstrap_components import Button


class bitmapImageLayoutIDs:
    id_type_base: str
    index: int | None
    prop_names: tuple[str, ...] = ("div", "graph", "slider", "refresh", "delete")

    def __init__(
        self, id_type_base: str = "bitmap-image", index: int | None = None
    ) -> None:
        self.id_type_base = id_type_base
        self.index = index

    @property
    def div(self) -> str:
        return self.full_id("-div")

    @property
    def graph(self) -> str:
        return self.full_id("-graph")

    @property
    def slider(self) -> str:
        return self.full_id("-slider")

    @property
    def refresh(self) -> str:
        return self.full_id("-refresh")

    @property
    def delete(self) -> str:
        return self.full_id("-delete")

    def full_id(self, id_suffix: str) -> str:
        return self.id_type_base + id_suffix

    def get_id_with_index(self, prop: str) -> dict[str, str | int]:
        full_id: dict[str, str | int] = {"type": str(getattr(self, prop))}
        if self.index is not None:
            full_id["index"] = self.index
        return full_id


def bitmap_image_layout(
    index: int,
    id_type_base: str = "bitmap-image",
    slider_bg_hexcolor: str = "#FFFFFF",
    button_label: str = "Refresh Image",
    delete_button_label: str = "Delete Image",
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_init_range: tuple[float, float] = (1.65, 1.9),
    slider_step: float = 0.1,
) -> tuple[html.Div, bitmapImageLayoutIDs]:

    imIDs = bitmapImageLayoutIDs(id_type_base=id_type_base, index=index)

    fig_image = dcc.Graph(
        id=imIDs.get_id_with_index("graph"),
        config={
            "modeBarButtonsToAdd": [
                # "drawclosedpath",
                # "drawcircle",
                "drawrect",
                "eraseshape",
            ]
        },
    )

    energy_range = dcc.RangeSlider(
        slider_start,
        slider_stop,
        step=slider_step,
        value=slider_init_range,
        id=imIDs.get_id_with_index("slider"),
        className="text-info",
    )

    _primary_graph_div = html.Div(
        [
            html.Div(energy_range, style={"background": slider_bg_hexcolor}),
            Button(button_label, id=imIDs.get_id_with_index("refresh")),
            Button(
                delete_button_label,
                id=imIDs.get_id_with_index("delete"),
            ),
            fig_image,
        ],
        id=imIDs.get_id_with_index("div"),
        className="col-lg-4",
        style={"padding": "10px"},
    )

    return _primary_graph_div, imIDs

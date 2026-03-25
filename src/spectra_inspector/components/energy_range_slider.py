import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, callback, ctx, dcc, no_update

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.element_energy_ranges import element_energy_ranges_keV


class elementDropdownSliderIDS(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "dropdown",
        "slider",
    )

    def __init__(
        self, id_type_base: str = "element-dropdown-slider", index: int | None = None
    ):
        super().__init__(id_type_base, index)

    @property
    def dropdown(self) -> str:
        return self.full_id("-dropdown")

    @property
    def slider(self) -> str:
        return self.full_id("-slider")


def get_element_dropdown_and_slider(
    id_type_base: str = "element-dropdown-slider",
    index: int = 0,
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
) -> tuple[dbc.Row, elementDropdownSliderIDS]:

    layoutIDs = elementDropdownSliderIDS(id_type_base, index=index)

    elements = list(element_energy_ranges_keV.keys())
    element_selector = dcc.Dropdown(
        ["none", *elements],
        value=elements[0],
        id=layoutIDs.get_id_with_index("dropdown"),
        className="text-info",
    )

    slider_init_range = element_energy_ranges_keV[elements[0]]
    energy_range = dcc.RangeSlider(
        slider_start,
        slider_stop,
        step=slider_step,
        value=slider_init_range,
        id=layoutIDs.get_id_with_index("slider"),
        className="text-info",
    )

    row = dbc.Row(
        [
            dbc.Col(element_selector),
            dbc.Col(energy_range, width=9),
        ],
        align="center",
    )

    return row, layoutIDs


_imageSliderIds = elementDropdownSliderIDS()


@callback(
    Output({"type": _imageSliderIds.slider, "index": MATCH}, "value"),
    Output({"type": _imageSliderIds.dropdown, "index": MATCH}, "value"),
    Input({"type": _imageSliderIds.dropdown, "index": MATCH}, "value"),
    Input({"type": _imageSliderIds.slider, "index": MATCH}, "value"),
)
def sync_element_selector_dropdown(
    element_name: str, slider_range: tuple[float, float]
):
    triggered_id = ctx.triggered_id
    if triggered_id is None or "type" not in triggered_id:
        return no_update, no_update
    if triggered_id["type"] == _imageSliderIds.dropdown:
        if element_name == "none" or element_name is None:
            return no_update, no_update
        return element_energy_ranges_keV[element_name], no_update
    if triggered_id["type"] == _imageSliderIds.slider:
        return slider_range, "none"
    msg = "unexpected trigger."
    raise RuntimeError(msg)

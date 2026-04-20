import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, callback, ctx, dcc, no_update

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.element_energy_ranges import element_energy_ranges_keV


class elementDropdownSliderIDS(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "dropdown",
        "slider",
        "collapse",
        "collapsebutton",
        "refreshbutton",
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

    @property
    def collapse(self) -> str:
        return self.full_id("-collapse")

    @property
    def collapsebutton(self) -> str:
        return self.full_id("-collapsebutton")

    @property
    def refreshbutton(self) -> str:
        return self.full_id("-refreshbutton")


def get_element_dropdown_and_slider(
    id_type_base: str = "element-dropdown-slider",
    index: int = 0,
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
    init_element_id: int = 0,
) -> tuple[dbc.Container, elementDropdownSliderIDS]:

    layoutIDs = elementDropdownSliderIDS(id_type_base, index=index)

    elements = list(element_energy_ranges_keV.keys())
    element_selector = dcc.Dropdown(
        ["none", *elements],
        value=elements[init_element_id],
        id=layoutIDs.get_id_with_index("dropdown"),
        className="text-info",
        searchable=False,
        clearable=False,
    )

    slider_init_range = element_energy_ranges_keV[elements[init_element_id]]

    energy_marks = {val: val for val in range(0, 16, 3)}

    energy_range = dbc.Card(
        dbc.CardBody(
            [
                dcc.RangeSlider(
                    slider_start,
                    slider_stop,
                    step=slider_step,
                    value=slider_init_range,
                    id=layoutIDs.get_id_with_index("slider"),
                    className="text-info",
                    marks=energy_marks,
                )
            ]
        ),
        color="light",
    )

    element_selector_row = dbc.Row(
        [
            dbc.Col(element_selector, width=4),
            dbc.Col(width=4),
            dbc.Col(
                dbc.Button(
                    "Apply",
                    id=layoutIDs.get_id_with_index("refreshbutton"),
                    color="secondary",
                ),
                width=2,
            ),
        ]
    )

    range_row = dbc.Row(
        [
            dbc.Col(energy_range, width=12),
            dbc.Tooltip(
                "Adjust endpoints to set energy bounds (keV)",
                target=layoutIDs.get_id_with_index("slider"),
            ),
        ],
        align="center",
    )

    collapse_button = dbc.Button(
        "Adjust energy bounds",
        id=layoutIDs.get_id_with_index("collapsebutton"),
        className="mb-3",
        color="secondary",
        n_clicks=0,
    )

    slider_collapse = dbc.Collapse(
        dbc.Card(dbc.CardBody(range_row)),
        id=layoutIDs.get_id_with_index("collapse"),
        is_open=False,
    )

    cont = dbc.Container(
        [
            element_selector_row,
            collapse_button,
            slider_collapse,
            dbc.Tooltip(
                "Click to show or hide the manual energy range adjustment panel",
                target=layoutIDs.get_id_with_index("collapsebutton"),
            ),
            dbc.Tooltip(
                "Click to apply any changes in element or energy bounds range",
                target=layoutIDs.get_id_with_index("refreshbutton"),
            ),
            dbc.Tooltip(
                "Select an element map",
                target=layoutIDs.get_id_with_index("dropdown"),
            ),
        ]
    )

    return cont, layoutIDs


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


@callback(
    Output({"type": _imageSliderIds.collapse, "index": MATCH}, "is_open"),
    [Input({"type": _imageSliderIds.collapsebutton, "index": MATCH}, "n_clicks")],
    [State({"type": _imageSliderIds.collapse, "index": MATCH}, "is_open")],
)
def toggle_energy_slider_collapse(n, is_open):
    if n:
        return not is_open
    return is_open

from dataclasses import dataclass, field

import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, callback, ctx, dcc, no_update
from dash.development.base_component import Component

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.element_energy_ranges import (
    get_element_energy_ranges,
)


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


@dataclass
class elementDropdownSliderParts:
    """The pieces of the element/energy-range selector, so a panel can place
    them in its own layout (the dropdown and Apply in a card header, the
    collapse toggle beside other controls) rather than as one block."""

    dropdown: dcc.Dropdown
    apply_button: dbc.Button
    collapse_button: dbc.Button
    collapse: dbc.Collapse
    tooltips: list[Component] = field(default_factory=list)


def build_element_dropdown_and_slider(
    id_type_base: str = "element-dropdown-slider",
    index: int = 0,
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
    init_element: str | None = None,
) -> tuple[elementDropdownSliderParts, elementDropdownSliderIDS]:
    """``init_element`` picks the preset the panel starts on; when it is not
    among the server's presets (or is None) the first preset is used."""

    layoutIDs = elementDropdownSliderIDS(id_type_base, index=index)

    element_ranges = get_element_energy_ranges()
    elements = list(element_ranges)
    elements.sort()
    if init_element not in element_ranges:
        init_element = elements[0]
    element_selector = dcc.Dropdown(
        ["none", *elements],
        value=init_element,
        id=layoutIDs.get_id_with_index("dropdown"),
        className="text-info",
        searchable=False,
        clearable=False,
        style={"minWidth": "7rem"},
    )

    slider_init_range = element_ranges[init_element]

    energy_marks = {val: val for val in range(0, 16, 3)}

    energy_range = dbc.Card(
        dbc.CardBody(
            dcc.RangeSlider(
                slider_start,
                slider_stop,
                step=slider_step,
                value=slider_init_range,
                id=layoutIDs.get_id_with_index("slider"),
                className="text-info",
                marks=energy_marks,
            ),
            className="pb-1 pt-3 px-2",
        ),
        color="light",
        className="mb-2",
    )

    apply_button = dbc.Button(
        "Apply",
        id=layoutIDs.get_id_with_index("refreshbutton"),
        color="secondary",
    )

    collapse_button = dbc.Button(
        "Adjust energy bounds",
        id=layoutIDs.get_id_with_index("collapsebutton"),
        color="secondary",
        n_clicks=0,
        className="text-nowrap",
    )

    slider_collapse = dbc.Collapse(
        energy_range,
        id=layoutIDs.get_id_with_index("collapse"),
        is_open=False,
    )

    tooltips: list[Component] = [
        dbc.Tooltip(
            "Adjust endpoints to set energy bounds (keV)",
            target=layoutIDs.get_id_with_index("slider"),
        ),
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

    parts = elementDropdownSliderParts(
        dropdown=element_selector,
        apply_button=apply_button,
        collapse_button=collapse_button,
        collapse=slider_collapse,
        tooltips=tooltips,
    )
    return parts, layoutIDs


def get_element_dropdown_and_slider(
    id_type_base: str = "element-dropdown-slider",
    index: int = 0,
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
    init_element: str | None = None,
) -> tuple[dbc.Container, elementDropdownSliderIDS]:
    """The selector as one self-contained block; see
    `build_element_dropdown_and_slider` for the pieces."""

    parts, layoutIDs = build_element_dropdown_and_slider(
        id_type_base=id_type_base,
        index=index,
        slider_start=slider_start,
        slider_stop=slider_stop,
        slider_step=slider_step,
        init_element=init_element,
    )

    element_selector_row = dbc.Row(
        [
            dbc.Col(parts.dropdown, width="auto"),
            dbc.Col(parts.apply_button, width="auto"),
            dbc.Col(parts.collapse_button, width="auto"),
        ],
        align="center",
        className="g-2 mb-2",
    )

    cont = dbc.Container(
        [element_selector_row, parts.collapse, *parts.tooltips],
        fluid=True,
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
        element_range = get_element_energy_ranges().get(element_name)
        if element_range is None:
            return no_update, no_update
        return element_range, no_update
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

import pytest

from spectra_inspector.components import energy_range_slider as ers

_RANGES = {"Na": (0.96, 1.12), "Mg": (1.13, 1.34), "Al": (1.40, 1.61)}
_PATCH_TARGET = (
    "spectra_inspector.components.energy_range_slider.get_element_energy_ranges"
)


@pytest.fixture
def server_ranges(mocker):
    mocker.patch(_PATCH_TARGET, return_value=dict(_RANGES))
    return _RANGES


def _find(component, component_id):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, list):
        children = [children]
    for child in children:
        found = _find(child, component_id)
        if found is not None:
            return found
    return None


def _dropdown_and_slider(cont, ids):
    dropdown = _find(cont, ids.get_id_with_index("dropdown"))
    slider = _find(cont, ids.get_id_with_index("slider"))
    assert dropdown is not None
    assert slider is not None
    return dropdown, slider


def test_dropdown_offers_the_server_presets(server_ranges):
    cont, ids = ers.get_element_dropdown_and_slider(index=3)
    dropdown, slider = _dropdown_and_slider(cont, ids)

    els = ["Na", "Mg", "Al"]
    els.sort()
    assert dropdown.options == ["none", *els]
    assert dropdown.value == els[0]
    assert slider.value == server_ranges[els[0]]


def test_init_element_is_honoured(server_ranges):
    cont, ids = ers.get_element_dropdown_and_slider(init_element="Al")
    dropdown, slider = _dropdown_and_slider(cont, ids)

    assert dropdown.value == "Al"
    assert slider.value == server_ranges["Al"]


def test_unknown_init_element_falls_back_to_the_first_preset(server_ranges):
    cont, ids = ers.get_element_dropdown_and_slider(init_element="Xx")
    dropdown, slider = _dropdown_and_slider(cont, ids)

    els = list(_RANGES.keys())
    els.sort()
    assert dropdown.value == els[0]
    assert slider.value == server_ranges[els[0]]


@pytest.fixture
def triggered_by(mocker):
    def _set(component_type):
        mocker.patch.object(
            type(ers.ctx),
            "triggered_id",
            new_callable=mocker.PropertyMock,
            return_value={"type": component_type, "index": 0},
        )

    return _set


def test_picking_an_element_moves_the_slider(server_ranges, triggered_by):
    triggered_by(ers._imageSliderIds.dropdown)

    slider_value, dropdown_value = ers.sync_element_selector_dropdown("Mg", (0, 1))

    assert slider_value == server_ranges["Mg"]
    assert dropdown_value is ers.no_update


@pytest.mark.usefixtures("server_ranges")
def test_picking_an_unknown_element_changes_nothing(triggered_by):
    triggered_by(ers._imageSliderIds.dropdown)

    assert ers.sync_element_selector_dropdown("Xx", (0, 1)) == (
        ers.no_update,
        ers.no_update,
    )


@pytest.mark.usefixtures("server_ranges")
def test_moving_the_slider_clears_the_element(triggered_by):
    triggered_by(ers._imageSliderIds.slider)

    assert ers.sync_element_selector_dropdown("Mg", (2.0, 3.0)) == (
        (2.0, 3.0),
        "none",
    )

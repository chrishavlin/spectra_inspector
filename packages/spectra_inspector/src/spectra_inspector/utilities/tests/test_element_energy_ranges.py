from spectra_inspector.utilities.element_energy_ranges import (
    get_element_energy_ranges,
)
from spectra_inspector.utilities.model import ElementEnergyRanges


def test_ranges_follow_the_server_model_in_field_order():
    ranges = get_element_energy_ranges()

    assert list(ranges) == list(ElementEnergyRanges.model_fields)
    assert "Mg" in ranges
    assert len(ranges) >= 9


def test_ranges_are_float_tuples():
    for window in get_element_energy_ranges().values():
        assert isinstance(window, tuple)
        assert len(window) == 2
        assert all(isinstance(bound, float) for bound in window)
        assert window[0] < window[1]


def test_callers_cannot_mutate_the_table():
    get_element_energy_ranges().pop("Mg")

    assert "Mg" in get_element_energy_ranges()

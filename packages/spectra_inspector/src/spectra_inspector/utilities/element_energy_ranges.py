"""Element presets for the energy-range slider.

The server integrates each element's peak over a fixed keV window and ships
that table as the defaults of ``ElementEnergyRanges`` (part of its ``/info``
response), so it arrives here through the generated models: the dropdown offers
exactly the windows the reported weights use, with no request.
"""

from spectra_inspector.utilities.model import ElementEnergyRanges

ElementRanges = dict[str, tuple[float, float]]


def get_element_energy_ranges() -> ElementRanges:
    """The server's element windows in keV, keyed by symbol in server order."""
    return {
        element: (float(window[0]), float(window[1]))
        for element, window in ElementEnergyRanges()
        if window is not None
    }

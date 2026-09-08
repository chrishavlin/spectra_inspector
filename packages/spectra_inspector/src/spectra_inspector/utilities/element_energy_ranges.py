"""Element presets for the energy-range slider, served by the backend.

The server integrates each element's peak over a fixed keV window
(``calibration.element_energy_ranges_keV``); the dropdown offers exactly those
windows so that the maps line up with the weights it reports. The table is a
server constant, so it is fetched once per process and kept.
"""

import threading

import requests

from spectra_inspector.logging import spectraLogger
from spectra_inspector.utilities.interface import (
    ServerRequestError,
    SpectraInspectorServerInterface,
)

ElementRanges = dict[str, tuple[float, float]]

_lock = threading.Lock()
_ranges: ElementRanges | None = None


def get_element_energy_ranges() -> ElementRanges:
    """The server's element windows in keV, keyed by symbol in server order.

    Returns an empty dict (and retries on the next call) while the backend
    cannot be reached, so a layout can still render without presets.
    """
    global _ranges  # noqa: PLW0603
    if _ranges is not None:
        return _ranges
    with _lock:
        if _ranges is None:
            fetched = _fetch()
            if fetched is not None:
                _ranges = fetched
    return dict(_ranges or {})


def _fetch() -> ElementRanges | None:
    try:
        ranges = SpectraInspectorServerInterface().get_element_energy_ranges()
    except (requests.exceptions.ConnectionError, ServerRequestError) as err:
        spectraLogger.warning("Could not fetch element energy ranges: %s", err)
        return None
    return {el: (float(e0), float(e1)) for el, (e0, e1) in ranges.ranges_keV.items()}


def reset_cache() -> None:
    """Forget the cached table so the next call fetches again (tests)."""
    global _ranges  # noqa: PLW0603
    with _lock:
        _ranges = None

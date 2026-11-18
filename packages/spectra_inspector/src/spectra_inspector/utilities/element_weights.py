"""How a spectrum's element weights are presented, shared by the page's table
and the summary exports."""

from collections.abc import Iterable
from typing import Any

WEIGHTS_UNAVAILABLE_MSG = "Weights unavailable for this map"

# whole-number counts, displayed without a fractional part
INTEGER_WEIGHT_KEYS: tuple[str, ...] = ("total_count", "counts_14_15_kev")


def apply_zeroed_elements(wts: dict, zeroed_elements: Iterable[str]) -> dict:
    """The weights with every element the user has zeroed out set to 0.0."""
    zeroed = set(zeroed_elements)
    return {key: (0.0 if key in zeroed else value) for key, value in wts.items()}


def format_weight(key: str, value: Any) -> str:
    # exact zeros and whole counts come back from the JSON store as ints
    if isinstance(value, int | float) and not isinstance(value, bool):
        if key in INTEGER_WEIGHT_KEYS:
            return f"{round(value):d}"
        return f"{value:.8f}"
    return str(value)


def element_weights_text(wts: dict) -> str:
    """The weights as tab separated ``name<TAB>value`` lines, unrounded."""
    return "".join(f"{element}\t{weight}\n" for element, weight in wts.items())


def zeroed_note(wts: dict, zeroed_elements: Iterable[str]) -> str | None:
    """The line naming the manually zeroed elements, None when there are none."""
    zeroed = [element for element in zeroed_elements if element in wts]
    if not zeroed:
        return None
    return f"Element weights were manually zeroed for: {', '.join(zeroed)}"

import pytest

from spectra_inspector.components.data_export_panel import (
    WEIGHTS_UNAVAILABLE_MSG,
    get_element_weights,
    get_formatted_element_weights,
)


@pytest.mark.parametrize(
    "metadata",
    [{}, {"attrs": {}}, {"attrs": {"weights": None}}, {"attrs": {"weights": {}}}],
)
def test_get_element_weights_missing(metadata):
    # the server sends a null weights for any spectrum it cannot calibrate
    # (issue #92); every consumer sees that as None.
    assert get_element_weights(metadata) is None


def test_get_element_weights():
    weights = {"Na": 0.5}
    assert get_element_weights({"attrs": {"weights": weights}}) == weights


def test_formatted_element_weights():
    weights = {"Na": 0.5, "total_count": 100.0}
    div = get_formatted_element_weights({"attrs": {"weights": weights}})

    assert div.children[0].content == "Na\t0.50000000\ntotal_count\t100.00000000"


@pytest.mark.parametrize("attrs", [{}, {"weights": None}])
def test_formatted_element_weights_unavailable(attrs):
    # the server hands back a null weights when it cannot calculate them
    # (issue #92); say so rather than rendering an empty panel.
    div = get_formatted_element_weights({"attrs": attrs})

    assert div.children == WEIGHTS_UNAVAILABLE_MSG


def test_formatted_element_weights_without_spectrum():
    assert get_formatted_element_weights({}).children is None

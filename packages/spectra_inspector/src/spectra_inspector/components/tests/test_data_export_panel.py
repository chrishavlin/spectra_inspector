import pytest

from spectra_inspector.components.data_export_panel import (
    RESTORE_SYMBOL,
    SUMMARY_WEIGHT_KEYS,
    WEIGHTS_UNAVAILABLE_MSG,
    ZERO_SYMBOL,
    apply_zeroed_elements,
    dataExportPanelIDS,
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

    assert div.children[0].content == "Na\t0.50000000\ntotal_count\t100"


@pytest.mark.parametrize("attrs", [{}, {"weights": None}])
def test_formatted_element_weights_unavailable(attrs):
    # the server hands back a null weights when it cannot calculate them
    # (issue #92); say so rather than rendering an empty panel.
    div = get_formatted_element_weights({"attrs": attrs})

    assert div.children == WEIGHTS_UNAVAILABLE_MSG


def test_formatted_element_weights_without_spectrum():
    assert get_formatted_element_weights({}).children is None


def test_data_export_panel_ids_round_trip():
    ids = dataExportPanelIDS(index=0)
    for prop in ids.prop_names:
        assert isinstance(getattr(ids, prop), str)


def test_zero_element_id_is_keyed_on_the_element():
    ids = dataExportPanelIDS(index=0)
    assert ids.zero_element_id("Na") == {"type": ids.zeroelement, "index": "Na"}


def test_apply_zeroed_elements():
    weights = {"Na": 0.5, "Si": 0.25, "total_count": 100.0}

    assert apply_zeroed_elements(weights, ["Si"]) == {
        "Na": 0.5,
        "Si": 0.0,
        "total_count": 100.0,
    }
    assert apply_zeroed_elements(weights, []) == weights


def _table_rows(div):
    return div.children[1].children.children


def test_swatch_is_muted_for_a_peak_that_is_not_drawn():
    # a zero weight, computed or zeroed out by the user, hides the element's
    # peak on the graph; its chip fades but keeps its colour so a reset is
    # recognisable
    metadata = {
        "attrs": {
            "weights": {"Si": 0.25, "Fe": 0.0},
            "integration_ranges_keV": {"Si": [1.645, 1.88], "Fe": [6.275, 6.54]},
        }
    }
    div = get_formatted_element_weights(metadata, ["Si"])
    swatches = {
        row.children[0].children[1]: row.children[0].children[0]
        for row in _table_rows(div)
    }
    assert swatches["Si"].style["opacity"] == 0.25
    assert swatches["Si"].title == "peak not drawn"
    assert swatches["Fe"].style["opacity"] == 0.25

    restored = get_formatted_element_weights(metadata, [])
    si_swatch = _table_rows(restored)[0].children[0].children[0]
    assert si_swatch.style["opacity"] == 1
    assert si_swatch.style["backgroundColor"] == swatches["Si"].style["backgroundColor"]


def test_formatted_element_weights_colour_coded_to_the_spectrum_windows():
    # every element with an integration window gets the swatch the spectrum
    # graph shades that window with; the summary rows stay plain (issue #120)
    from spectra_inspector.utilities.peak_windows import spectrum_element_colors

    metadata = {
        "attrs": {
            "weights": {"Si": 0.25, "Fe": 0.5, "total_count": 100.0},
            "integration_ranges_keV": {"Si": [1.645, 1.88], "Fe": [6.275, 6.54]},
        }
    }
    div = get_formatted_element_weights(metadata)
    colors = spectrum_element_colors(metadata)
    assert set(colors) == {"Si", "Fe"}

    name_cells = [row.children[0] for row in _table_rows(div)]
    swatch_si, key_si = name_cells[0].children
    assert key_si == "Si"
    assert swatch_si.style["backgroundColor"] == colors["Si"]
    swatch_fe, key_fe = name_cells[1].children
    assert key_fe == "Fe"
    assert swatch_fe.style["backgroundColor"] == colors["Fe"]
    assert swatch_fe.style["backgroundColor"] != swatch_si.style["backgroundColor"]
    assert name_cells[2].children == "total_count"
    assert swatch_si.style["opacity"] == 1
    assert swatch_si.title is None

    # the copied text is unchanged by the swatches
    assert div.children[0].content == "Si\t0.25000000\nFe\t0.50000000\ntotal_count\t100"


def test_formatted_element_weights_zeroed():
    # a zeroed element shows (and copies) as exactly zero, keeps the computed
    # value in its tooltip and its X becomes a restore arrow with the same id,
    # so one callback toggles the row; the summary rows never get a button.
    weights = {"Na": 0.5, "Si": 0.25, "total_count": 100.0, "DH_assessment": 0.1}
    div = get_formatted_element_weights({"attrs": {"weights": weights}}, ["Si"])

    assert div.children[0].content == (
        "Na\t0.50000000\nSi\t0.00000000\ntotal_count\t100\nDH_assessment\t0.10000000"
    )

    by_key = {row.children[0].children: row for row in _table_rows(div)}
    assert set(by_key) == set(weights)

    ids = dataExportPanelIDS(index=0)
    si_value, si_action = by_key["Si"].children[1:]
    assert si_value.children == "0.00000000"
    assert si_value.title == "computed: 0.25000000"
    assert si_action.children.children == RESTORE_SYMBOL
    assert si_action.children.title == "Restore Si"
    assert si_action.children.id == ids.zero_element_id("Si")

    na_value, na_action = by_key["Na"].children[1:]
    assert na_value.title is None
    assert na_action.children.children == ZERO_SYMBOL
    assert na_action.children.title == "Zero out Na"
    assert na_action.children.id == ids.zero_element_id("Na")

    for key in SUMMARY_WEIGHT_KEYS:
        if key in by_key:
            assert by_key[key].children[2].children is None


def test_formatted_element_weights_ints():
    # dcc.Store round-trips whole-number floats (and the server's clamped
    # zeros) as ints; element weights still format as floats.
    div = get_formatted_element_weights(
        {"attrs": {"weights": {"Na": 0, "total_count": 100}}}
    )

    assert div.children[0].content == "Na\t0.00000000\ntotal_count\t100"


def test_formatted_element_weights_count_rows_are_integers():
    # the two raw count rows display as whole numbers whether they arrive as
    # int or float; the ratio and per-element rows keep their 8 decimals.
    weights = {
        "Na": 0.5,
        "total_count": 12345.0,
        "counts_14_15_kev": 678,
        "DH_assessment": 0.25,
    }
    div = get_formatted_element_weights({"attrs": {"weights": weights}})

    assert div.children[0].content == (
        "Na\t0.50000000\ntotal_count\t12345\ncounts_14_15_kev\t678\nDH_assessment\t0.25000000"
    )
    by_key = {row.children[0].children: row for row in _table_rows(div)}
    assert by_key["total_count"].children[1].children == "12345"
    assert by_key["counts_14_15_kev"].children[1].children == "678"

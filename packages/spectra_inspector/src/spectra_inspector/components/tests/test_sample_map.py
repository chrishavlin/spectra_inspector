import pytest

from spectra_inspector.components import sample_map


def _options(*names: str) -> list[dict]:
    return [{"label": n, "value": n} for n in ("none", *names)]


def test_sample_id_from_click_data_reads_last_customdata_column():
    click = {"points": [{"customdata": ["granite", 12.0, "C-29"]}]}
    assert sample_map.sample_id_from_click_data(click) == "C-29"


def test_sample_id_from_click_data_scalar_customdata():
    click = {"points": [{"customdata": "C-29"}]}
    assert sample_map.sample_id_from_click_data(click) == "C-29"


@pytest.mark.parametrize(
    "click", [None, {}, {"points": []}, {"points": [{"lat": 1.0, "lon": 2.0}]}]
)
def test_sample_id_from_click_data_handles_missing(click):
    assert sample_map.sample_id_from_click_data(click) is None


def test_dataset_for_sample_single_match():
    opts = _options("C-12", "C-29 Map 1", "C-29 Map 2")
    assert sample_map.dataset_for_sample("C-12", opts, None) == "C-12"


def test_dataset_for_sample_picks_first_of_several():
    opts = _options("C-12", "C-29 Map 1", "C-29 Map 2")
    assert sample_map.dataset_for_sample("C-29", opts, None) == "C-29 Map 1"
    assert sample_map.dataset_for_sample("C-29", opts, "C-12") == "C-29 Map 1"


def test_dataset_for_sample_keeps_current_selection_of_same_sample():
    opts = _options("C-12", "C-29 Map 1", "C-29 Map 2")
    assert sample_map.dataset_for_sample("C-29", opts, "C-29 Map 2") == "C-29 Map 2"


def test_dataset_for_sample_no_match():
    opts = _options("C-12", "C-29 Map 1")
    assert sample_map.dataset_for_sample("C-99", opts, None) is None
    assert sample_map.dataset_for_sample(None, opts, None) is None
    assert sample_map.dataset_for_sample("C-12", None, None) is None


def test_dataset_for_sample_never_returns_none_option():
    assert sample_map.dataset_for_sample("none", _options("C-12"), None) is None

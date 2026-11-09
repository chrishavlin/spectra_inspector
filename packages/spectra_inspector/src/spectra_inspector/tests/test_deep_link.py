"""A full page load of ``/inspector/<encoded name>`` (a pasted link or a
browser refresh) must put the real sample name, not the URL spelling, into
the dropdown the backend requests are keyed on and into the hidden
``sample-name`` div the figure callbacks read."""

import pytest
from dash import html
from dash.dcc import Dropdown

from spectra_inspector.components.dataset_selector import datasetSelectorLayoutIDs
from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import AvailableDatasets
from spectra_inspector.utilities.sample_url import sample_name_to_url

SAMPLE = "/TorresBoxSamples/test of server data/EN13/map20260930091127284_0.spd"


@pytest.fixture
def inspector(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app  # noqa: F401
    from spectra_inspector.pages import inspector

    monkeypatch.setattr(
        SpectraInspectorServerInterface,
        "get_available_datasets",
        lambda self, **kwargs: AvailableDatasets(available_files=[SAMPLE]),  # noqa: ARG005
    )
    return inspector


def _find(layout, predicate):
    return next(c for c in layout._traverse() if predicate(c))


def test_deep_link_layout_decodes_the_sample_name(inspector):
    url_segment = sample_name_to_url(SAMPLE)
    assert url_segment != SAMPLE

    layout = inspector.layout(sample_name=url_segment)

    dropdown_id = datasetSelectorLayoutIDs(index=1).get_id_with_index("dropdown")
    dropdown = _find(
        layout,
        lambda c: isinstance(c, Dropdown) and getattr(c, "id", None) == dropdown_id,
    )
    assert dropdown.value == SAMPLE
    assert SAMPLE in [o["value"] for o in dropdown.options]

    name_div = _find(
        layout,
        lambda c: (
            isinstance(c, html.Div)
            and getattr(c, "id", None) == inspector._IDS.sample_name
        ),
    )
    assert name_div.children == SAMPLE


def test_deep_link_layout_without_a_sample(inspector):
    layout = inspector.layout(sample_name="none")
    name_div = _find(
        layout,
        lambda c: (
            isinstance(c, html.Div)
            and getattr(c, "id", None) == inspector._IDS.sample_name
        ),
    )
    assert name_div.children == "none"

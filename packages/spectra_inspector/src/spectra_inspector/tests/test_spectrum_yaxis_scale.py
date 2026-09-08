"""The spectrum plot's linear/log y-axis toggle (issue #130)."""

import pytest

from spectra_inspector.settings import ENV_PREFIX

SPECTRUM_GRAPH = "spectrum-container"
TOGGLE = "spectrum-yaxis-scale"


@pytest.fixture
def callbacks(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app._callback_list


def _dep_ids(deps: list[dict]) -> set[str]:
    return {str(dep.get("id")) for dep in deps}


def test_toggle_patches_the_spectrum_figure_without_refetching(callbacks):
    toggle_callbacks = [cb for cb in callbacks if TOGGLE in _dep_ids(cb["inputs"])]
    assert len(toggle_callbacks) == 1
    (toggle,) = toggle_callbacks
    assert SPECTRUM_GRAPH in toggle["output"]
    assert "full-spectrum-store" not in _dep_ids(toggle["state"])
    assert "active-shapes" not in _dep_ids(toggle["inputs"])


def test_spectrum_creation_reads_the_toggle(callbacks):
    spectrum_builders = [
        cb
        for cb in callbacks
        if "active-shapes" in _dep_ids(cb["inputs"]) and SPECTRUM_GRAPH in cb["output"]
    ]
    assert len(spectrum_builders) == 1
    assert TOGGLE in _dep_ids(spectrum_builders[0]["state"])


@pytest.mark.parametrize(
    ("scale", "expected"),
    [("linear", "linear"), ("log", "log"), (None, "linear"), ("bogus", "linear")],
)
def test_new_spectrum_figure_yaxis_type(scale, expected):
    from spectra_inspector.pages.inspector import new_spectrum_figure

    fig = new_spectrum_figure([0.0, 1.0, 2.0], [1.0, 10.0, 100.0], scale)

    assert fig.layout.yaxis.type == expected
    assert fig.layout.yaxis.title.text == "Intensity"
    assert fig.layout.xaxis.title.text == "Energy (keV)"
    assert fig.data[0].mode == "lines"


def _find(component, target_id):
    if getattr(component, "id", None) == target_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, list):
        children = [children]
    for child in children:
        found = _find(child, target_id)
        if found is not None:
            return found
    return None


def test_toggle_defaults_to_linear():
    from spectra_inspector.pages.inspector import _IDS, layout

    toggle = _find(layout(sample_name=None), _IDS.spectrum_yaxis_scale)

    assert toggle is not None
    assert toggle.value == "linear"
    assert [o["value"] for o in toggle.options] == ["linear", "log"]

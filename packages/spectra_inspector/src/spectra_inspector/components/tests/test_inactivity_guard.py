from pathlib import Path

import pytest

import spectra_inspector
from spectra_inspector.components import inactivity_guard as ig
from spectra_inspector.settings import ENV_PREFIX, Settings

_SCRIPT = Path(spectra_inspector.__file__).parent / "assets" / "inactivity_guard.js"


def _find(component, component_id):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, list | tuple):
        children = [children]
    for child in children:
        found = _find(child, component_id)
        if found is not None:
            return found
    return None


def _timeout(layout) -> int:
    return layout.to_plotly_json()["props"]["data-timeout-seconds"]


def test_dormant_outside_desktop_mode(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}INACTIVITY_TIMEOUT_SECONDS", "60")
    assert _timeout(ig.inactivity_guard()) == 0


def test_desktop_mode_passes_the_timeout_to_the_browser(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "true")
    assert _timeout(ig.inactivity_guard()) == 1800

    monkeypatch.setenv(f"{ENV_PREFIX}INACTIVITY_TIMEOUT_SECONDS", "60")
    assert _timeout(ig.inactivity_guard()) == 60

    monkeypatch.setenv(f"{ENV_PREFIX}INACTIVITY_TIMEOUT_SECONDS", "0")
    assert _timeout(ig.inactivity_guard()) == 0


def test_negative_timeout_is_rejected(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}INACTIVITY_TIMEOUT_SECONDS", "-1")
    with pytest.raises(ValueError, match="inactivity_timeout_seconds"):
        Settings()


def test_only_the_buttons_dismiss_the_modal():
    layout = ig.inactivity_guard()
    assert layout.id == ig.INACTIVITY_GUARD_ID

    modal = _find(layout, ig.INACTIVITY_MODAL_ID)
    assert modal.is_open is False
    assert modal.backdrop == "static"
    assert modal.keyboard is False

    assert _find(layout, ig.INACTIVITY_CONTINUE_ID) is not None
    # a real page load, which is what empties the memory stores
    new_session = _find(layout, ig.INACTIVITY_NEW_SESSION_ID)
    assert new_session.href == "/"
    assert new_session.external_link is True


@pytest.mark.parametrize("desktop_mode", [False, True])
def test_app_layout_carries_the_guard(desktop_mode, monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", str(desktop_mode).lower())

    from spectra_inspector.main import app

    guard = _find(app.layout(), ig.INACTIVITY_GUARD_ID)
    assert _timeout(guard) == (1800 if desktop_mode else 0)


def test_continue_is_a_clientside_callback():
    from spectra_inspector.main import app

    app._setup_server()
    writers = [
        cb for cb in app._callback_list if ig.INACTIVITY_MODAL_ID in cb["output"]
    ]
    assert len(writers) == 1
    (dismiss,) = writers
    assert dismiss["clientside_function"] == {
        "namespace": "inactivityGuard",
        "function_name": "dismiss",
    }
    assert dismiss["prevent_initial_call"]
    assert [(dep["id"], dep["property"]) for dep in dismiss["inputs"]] == [
        (ig.INACTIVITY_CONTINUE_ID, "n_clicks")
    ]


def test_script_agrees_with_the_layout_ids():
    script = _SCRIPT.read_text()
    assert f'SI_INACTIVITY_GUARD_ID = "{ig.INACTIVITY_GUARD_ID}"' in script
    assert f'SI_INACTIVITY_MODAL_ID = "{ig.INACTIVITY_MODAL_ID}"' in script
    assert "inactivityGuard: {" in script
    assert "dismiss: function" in script
    assert "dataset.timeoutSeconds" in script

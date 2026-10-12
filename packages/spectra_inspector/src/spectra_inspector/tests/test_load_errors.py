"""A backend failure during a sample load is reported on the page.

The spectrum and image load callbacks catch the interface's errors and write
the page's load-error alerts instead of dying (which left the panel blank in
prod, with a Dash 500 nobody sees). A busy server -- a 503 that survived the
interface's one automatic retry, or a 504 -- and an unreachable one get a
message with a Retry; a sample the server does not know gets "not found"
without one.
"""

import importlib

import dash
import pytest
import requests

from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.tests.test_export_summary import combined_metadata
from spectra_inspector.utilities import interface
from spectra_inspector.utilities.interface import ServerRequestError

SAMPLE = "C-12"
GRAPH_ID = {"type": "bitmap-image-graph", "index": 0}
REFRESH_ID = {"type": "element-dropdown-slider-refreshbutton", "index": 0}
COMPOSITE_APPLY_ID = {"type": "composite-image-apply", "index": 0}
ONE_PANEL = {
    "initialized": True,
    "active_div_ids": [{"type": "bitmap-image-div", "index": 0}],
    "next_index": 1,
}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    from spectra_inspector.main import app

    app._setup_server()
    return app


@pytest.fixture
def inspector(app):  # noqa: ARG001
    return importlib.import_module(dash.page_registry["pages.inspector"]["module"])


@pytest.fixture
def triggered_by(mocker, inspector):
    def _set(triggered_id, n_props: int = 1):
        mocker.patch.object(
            type(inspector.ctx),
            "triggered_id",
            new_callable=mocker.PropertyMock,
            return_value=triggered_id,
        )
        mocker.patch.object(
            type(inspector.ctx),
            "triggered_prop_ids",
            new_callable=mocker.PropertyMock,
            return_value={f"prop{i}": triggered_id for i in range(n_props)},
        )

    return _set


@pytest.fixture
def no_sleep(mocker):
    return mocker.patch.object(interface, "_sleep")


def _response(mocker, status_code: int, headers: dict | None = None):
    response = mocker.Mock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = {"detail": f"{SAMPLE} answered {status_code}"}
    return response


def _busy(mocker):
    return _response(mocker, 503, {"Retry-After": "2"})


class TestSpectrumLoad:
    def _load(self, inspector):
        return inspector.initialize_full_spectrum_data(
            SAMPLE, {}, 0, {"selected_dataset": SAMPLE}
        )

    def test_a_busy_server_is_retried_once_then_reported(
        self, inspector, mocker, no_sleep
    ):
        get = mocker.patch("requests.Session.get", return_value=_busy(mocker))

        store, is_open, message, retry_hidden = self._load(inspector)

        assert store is inspector.no_update
        assert is_open is True
        assert "busy" in message
        assert retry_hidden is False
        # one automatic retry after the server's Retry-After, no more
        assert get.call_count == 2
        no_sleep.assert_called_once_with(2.0)

    def test_a_timeout_is_busy_without_a_retry_of_its_own(
        self, inspector, mocker, no_sleep
    ):
        get = mocker.patch("requests.Session.get", return_value=_response(mocker, 504))

        store, is_open, message, retry_hidden = self._load(inspector)

        assert store is inspector.no_update
        assert is_open is True
        assert "busy" in message
        assert retry_hidden is False
        assert get.call_count == 1
        assert not no_sleep.called

    def test_an_unknown_sample_is_not_found_and_not_retryable(
        self, inspector, mocker, no_sleep
    ):
        mocker.patch("requests.Session.get", return_value=_response(mocker, 404))

        store, is_open, message, retry_hidden = self._load(inspector)

        assert store is inspector.no_update
        assert is_open is True
        assert "not found" in message.lower()
        assert retry_hidden is True
        assert not no_sleep.called

    def test_an_unreachable_backend_is_reported(self, inspector, mocker):
        mocker.patch(
            "requests.Session.get",
            side_effect=requests.exceptions.ConnectionError("refused"),
        )

        store, is_open, message, retry_hidden = self._load(inspector)

        assert store is inspector.no_update
        assert is_open is True
        assert "reach" in message.lower()
        assert retry_hidden is False

    def test_a_successful_load_closes_the_alert(self, inspector, mocker):
        ok = _response(mocker, 200)
        ok.json.return_value = {
            "energy": [0.0, 1.0],
            "intensity": [1.0, 2.0],
            "energy_min": 0.0,
            "energy_max": 1.0,
        }
        mocker.patch("requests.Session.get", return_value=ok)

        store, is_open, message, retry_hidden = self._load(inspector)

        assert store["intensity"] == [1.0, 2.0]
        assert is_open is False
        assert message is inspector.no_update
        assert retry_hidden is inspector.no_update

    def test_nothing_to_load_leaves_the_alert_alone(self, inspector):
        outputs = inspector.initialize_full_spectrum_data(
            "none", {}, 0, {"selected_dataset": "none"}
        )
        assert all(out is inspector.no_update for out in outputs)


class TestImageLoad:
    @pytest.fixture
    def metadata(self, mocker, inspector):
        return mocker.patch.object(
            inspector.UserStore,
            "conditionally_fetch_metadata",
            return_value=combined_metadata(),
        )

    def _build(self, inspector, processed=None):
        return inspector.update_graph_figure(
            [None],
            None,
            0,
            [REFRESH_ID],
            ["viridis"],
            ONE_PANEL,
            [[0.0, 1.0]],
            [GRAPH_ID],
            {"selected_dataset": SAMPLE},
            processed if processed is not None else {"initialized": False},
            SAMPLE,
            [None],
            None,
            None,
        )

    def test_a_busy_server_is_reported_with_a_retry(
        self, inspector, mocker, triggered_by, metadata
    ):
        triggered_by(REFRESH_ID)
        fetch = mocker.patch.object(
            inspector,
            "fetch_im_data_parallel",
            side_effect=ServerRequestError("busy", status_code=503),
        )

        processed_store = {"initialized": False}
        figs, processed, view, is_open, message, retry_hidden = self._build(
            inspector, processed_store
        )

        assert figs == [inspector.no_update]
        assert processed is inspector.no_update
        assert view is inspector.no_update
        assert is_open is True
        assert "busy" in message
        assert retry_hidden is False
        assert fetch.call_count == 1
        assert metadata.call_count == 1
        # the panel was not marked processed, so the Retry rebuilds it
        assert processed_store["graph_ids"] == []

    @pytest.mark.usefixtures("metadata")
    def test_an_unknown_sample_is_not_found(self, inspector, mocker, triggered_by):
        triggered_by(REFRESH_ID)
        mocker.patch.object(
            inspector,
            "fetch_im_data_parallel",
            side_effect=ServerRequestError("not a valid sample", status_code=404),
        )

        *_, is_open, message, retry_hidden = self._build(inspector)

        assert is_open is True
        assert "not found" in message.lower()
        assert retry_hidden is True

    def test_a_failed_metadata_fetch_is_reported_too(
        self, inspector, mocker, triggered_by
    ):
        triggered_by(REFRESH_ID)
        mocker.patch.object(
            inspector.UserStore,
            "conditionally_fetch_metadata",
            side_effect=requests.exceptions.ConnectionError("refused"),
        )
        fetch = mocker.patch.object(inspector, "fetch_im_data_parallel")

        *_, is_open, message, retry_hidden = self._build(inspector)

        assert is_open is True
        assert "reach" in message.lower()
        assert retry_hidden is False
        assert not fetch.called

    def test_the_retry_button_drives_both_builders(self, app):
        builders = [
            cb
            for cb in app._callback_list
            if "image-load-error.is_open" in cb["output"]
        ]
        assert len(builders) == 2
        for builder in builders:
            assert any(dep.get("id") == "image-retry" for dep in builder["inputs"])

    def test_a_retry_with_nothing_new_does_nothing(
        self, inspector, triggered_by, metadata
    ):
        triggered_by("image-retry")
        processed = {
            "initialized": True,
            "graph_ids": [{"type": "bitmap-image-graph", "index": 0}],
        }
        outputs = self._build(inspector, processed)
        assert outputs[0] == [inspector.no_update]
        assert all(out is inspector.no_update for out in outputs[1:])
        assert not metadata.called


class TestCompositeLoad:
    def _build(self, inspector):
        return inspector.update_composite_figure(
            [None],
            0,
            [COMPOSITE_APPLY_ID],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            ONE_PANEL,
            [GRAPH_ID],
            {"selected_dataset": SAMPLE},
            {"initialized": False},
            SAMPLE,
            None,
            None,
        )

    def test_a_busy_server_is_reported_with_a_retry(self, inspector, mocker):
        mocker.patch.object(
            inspector.UserStore,
            "conditionally_fetch_metadata",
            side_effect=ServerRequestError("timed out", status_code=504),
        )

        figs, processed, is_open, message, retry_hidden = self._build(inspector)

        assert figs == [inspector.no_update]
        assert processed is inspector.no_update
        assert is_open is True
        assert "busy" in message
        assert retry_hidden is False

    def test_an_unknown_sample_is_not_found(self, inspector, mocker):
        mocker.patch.object(
            inspector.UserStore,
            "conditionally_fetch_metadata",
            side_effect=ServerRequestError("not a valid sample", status_code=404),
        )

        *_, is_open, message, retry_hidden = self._build(inspector)

        assert is_open is True
        assert "not found" in message.lower()
        assert retry_hidden is True

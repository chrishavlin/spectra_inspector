"""Pins the contract of the autouse fixture in the package's ``conftest.py``:
no test sees the developer's ``.env`` or exported ``SPECTRA_INSPECTOR_*``
variables unless it sets them itself."""

import os
from pathlib import Path

import pytest

from spectra_inspector.settings import ENV_PREFIX, Settings


def test_no_prefixed_variables_reach_a_test() -> None:
    assert not [key for key in os.environ if key.startswith(ENV_PREFIX)]


def test_tests_run_from_an_empty_tmp_path(tmp_path: Path) -> None:
    assert Path.cwd().resolve() == tmp_path.resolve()
    assert not (Path.cwd() / ".env").exists()


def test_settings_are_the_defaults() -> None:
    s = Settings()
    for name, field in Settings.model_fields.items():
        assert getattr(s, name) == field.default, name


def test_a_test_can_still_set_a_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "true")
    assert Settings().desktop_mode is True

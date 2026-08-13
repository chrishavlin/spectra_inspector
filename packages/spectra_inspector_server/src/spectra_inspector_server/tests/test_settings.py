from pathlib import Path

import pytest

from spectra_inspector_server.dependencies import get_settings
from spectra_inspector_server.settings import ENV_PREFIX, Settings


def test_settings() -> None:
    s = get_settings()
    assert s.app_name


def test_prefixed_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{ENV_PREFIX}APP_NAME='renamed'\n"
        f"{ENV_PREFIX}DATA_ROOT='/some/data/root'\n"
        f"{ENV_PREFIX}HOST_DATA_ROOT='/some/host/data/root'\n"
        f"{ENV_PREFIX}ALLOW_DB_REFRESH=true\n"
        f"{ENV_PREFIX}DESKTOP_MODE=true\n"
        f"{ENV_PREFIX}LOG_LEVEL='debug'\n"
    )
    monkeypatch.chdir(tmp_path)

    s = Settings()
    assert s.app_name == "renamed"
    assert s.data_root == "/some/data/root"
    assert s.host_data_root == "/some/host/data/root"
    assert s.allow_db_refresh is True
    assert s.desktop_mode is True
    assert s.log_level == "DEBUG"  # normalized by the field validator


def test_unprefixed_env_file_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # unprefixed keys would otherwise be ignored without any indication that
    # the configured values are not in use. see issue #89.
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME='renamed'\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=f"APP_NAME -> {ENV_PREFIX}APP_NAME"):
        Settings()


def test_extra_env_file_keys_still_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{ENV_PREFIX}NOT_A_SETTING=1\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="extra_forbidden"):
        Settings()

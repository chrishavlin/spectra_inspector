import pytest

from spectra_inspector.settings import ENV_PREFIX, Settings


def test_defaults():
    s = Settings()
    assert s.app_name
    assert s.server_port == 8000


def test_prefixed_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{ENV_PREFIX}APP_NAME = 'renamed'\n"
        f"{ENV_PREFIX}WRITE_DIR = '/some/tmp/dir'\n"
        f"{ENV_PREFIX}MAX_TMP_DIRS = 7\n"
        f"{ENV_PREFIX}SERVER_HOST = 'not-localhost'\n"
        f"{ENV_PREFIX}SERVER_PORT = 9001\n"
    )
    monkeypatch.chdir(tmp_path)

    s = Settings()
    assert s.app_name == "renamed"
    assert s.write_dir == "/some/tmp/dir"
    assert s.max_tmp_dirs == 7
    assert s.server_host == "not-localhost"
    assert s.server_port == 9001


def test_unprefixed_env_file_raises(tmp_path, monkeypatch):
    # unprefixed keys would otherwise be ignored without any indication that
    # the configured values are not in use. see issue #89.
    env_file = tmp_path / ".env"
    env_file.write_text("WRITE_DIR = '/some/tmp/dir'\nMAX_TMP_DIRS = 7\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=f"MAX_TMP_DIRS -> {ENV_PREFIX}MAX_TMP_DIRS"):
        Settings()


def test_extra_env_file_keys_still_raise(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(f"{ENV_PREFIX}NOT_A_SETTING = 1\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="extra_forbidden"):
        Settings()

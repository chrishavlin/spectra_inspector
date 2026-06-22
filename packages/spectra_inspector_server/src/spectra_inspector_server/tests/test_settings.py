from spectra_inspector_server.dependencies import get_settings


def test_settings() -> None:
    s = get_settings()
    assert s.app_name

from spectra_inspector.server.dependencies import get_settings


def test_settings() -> None:
    s = get_settings()
    assert s.app_name

import os
from pathlib import Path

import pytest

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server.settings import ENV_PREFIX


@pytest.fixture(autouse=True)
def _isolate_from_local_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep a developer's ``.env`` and exported ``SPECTRA_INSPECTOR_*`` variables
    out of the tests.

    ``Settings`` reads ``.env`` from the working directory, so every test runs
    from its own empty ``tmp_path``; a test that wants an env file writes one
    there. Values a test needs go through ``monkeypatch.setenv``.
    """
    for key in list(os.environ):
        if key.startswith(ENV_PREFIX):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="session")
def edax_path_handler() -> EDAXPathHandler:
    root_dir = "primary_edax_structure"
    return EDAXPathHandler(root_dir, require_valid_path=False)

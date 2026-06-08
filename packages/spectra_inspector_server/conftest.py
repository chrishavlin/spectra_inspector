import pytest

from spectra_inspector_server._file_tree_handling import EDAXPathHandler


@pytest.fixture(scope="session")
def edax_path_handler() -> EDAXPathHandler:
    root_dir = "primary_edax_structure"
    return EDAXPathHandler(root_dir, require_valid_path=False)

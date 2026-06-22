# mypy: disable-error-code="no-untyped-def"
from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._testing import _on_disc_mock
from spectra_inspector_server.model import EDAX_raw_ds


def test_PathHandler(tmp_path):

    root_dir = tmp_path / "spectra_root"
    root_dir.mkdir()
    ph = EDAXPathHandler(root_dir)

    EDAX_files = ph.get_sample_edax_file_names("C2")
    assert EDAX_files.spc.suffix == ".spc"


def test_path_handler_fixture(edax_path_handler):
    fake_filename = _on_disc_mock.filenames[0]
    ds = edax_path_handler.load_edax(fake_filename)
    assert isinstance(ds, EDAX_raw_ds)

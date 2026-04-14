from spectra_inspector.settings import Settings
from spectra_inspector.utilities.summary_writer import summaryWriter


def test_summary_writer_cleanup(tmp_path):
    write_dir = tmp_path / "summary_dir"
    write_dir.mkdir()

    settings = Settings()
    settings.max_tmp_dirs = 2
    settings.write_dir = write_dir

    for _ in range(settings.max_tmp_dirs * 4):
        _ = summaryWriter(settings=settings)

    existing_dirs = [f for f in write_dir.glob("*") if f.is_dir()]
    assert len(existing_dirs) == settings.max_tmp_dirs + 1

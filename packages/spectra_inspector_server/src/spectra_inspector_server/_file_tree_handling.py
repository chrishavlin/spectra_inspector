import os
from pathlib import Path

from spectra_inspector_server._database import OnDiskDatabase
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server._testing import _on_disc_mock
from spectra_inspector_server.model import EDAX_file_set, EDAX_raw_ds
from spectra_inspector_server.processor.file_loaders import (
    load_edax_spc,
    load_edax_spd,
)

_ENV_DATA_ROOT = "SPECTRAINSPECTORDATAROOT"


class EDAXPathHandler:
    data_root: Path
    database: OnDiskDatabase

    def __init__(
        self,
        data_root: str | Path | None = None,
        require_valid_path: bool = True,
        init_db: bool = False,
        allow_mixed_basenames: bool = False,
        max_datasets: int | None = None,
    ):

        valid_data_path: Path | None = None
        if data_root is None:
            if envval := os.environ.get(_ENV_DATA_ROOT):
                valid_data_path = Path(envval)
        else:
            valid_data_path = Path(data_root)

        if valid_data_path is None:
            msg = f"Could not identify data root directory, provide to PathHandler or set the environment variable {_ENV_DATA_ROOT}"
            raise ValueError(msg)

        self.data_root = Path(valid_data_path)

        if not Path.exists(self.data_root) and require_valid_path:
            msg = f"data_root path does not exist: {self.data_root}"
            raise FileNotFoundError(msg)

        self.database = OnDiskDatabase(
            self,
            init_db=init_db,
            allow_mixed_basenames=allow_mixed_basenames,
            max_datasets=max_datasets,
        )

        nmaps = len(self.database.available_maps)
        spectraLogger.info(
            f"Initialized PathHandler with data_root {self.data_root} with {nmaps} EDAX sets."
        )

    def refresh(self) -> None:
        spectraLogger.info("re-initializing PathHandler database")
        self.database.refresh(self)

    def set_working_directory(
        self, directory: str | Path, recursive: bool = True
    ) -> Path:
        """Restrict the database to a single directory beneath the data root.

        ``directory`` must already have been validated as being within
        ``self.data_root`` (see ``_file_browser.resolve_within_root``).
        """
        return self.database.set_working_directory(self, directory, recursive=recursive)

    @property
    def working_directory(self) -> Path:
        return self.database.working_directory or self.data_root

    def get_sample_edax_file_names(self, sample_name: str) -> EDAX_file_set | None:
        return self.database.available_maps.get(sample_name, None)

    def get_sample_spc_file(self, sample_name: str) -> Path | None:
        return self.database.available_spectra.get(sample_name, None)

    def load_edax(
        self,
        sample_name: str,
        metadata_only: bool = False,
        spectrum_only: bool = False,
    ) -> EDAX_raw_ds:
        """Load a sample, as the map of its file set or, with
        ``spectrum_only``, as the 1D spectrum of its ``.spc`` alone."""
        if _on_disc_mock.is_mock(sample_name, spectrum_only=spectrum_only):
            # a short-circuit for testing
            return _on_disc_mock.load(sample_name, spectrum_only=spectrum_only)

        if spectrum_only:
            spc = self.database.available_spectra.get(sample_name, None)
            if spc:
                return load_edax_spc(spc)
        else:
            files = self.database.available_maps.get(sample_name, None)
            if files:
                return load_edax_spd(files, metadata_only=metadata_only)

        kind = "spectrum" if spectrum_only else "map"
        msg = f"{sample_name} does not exist in database as a {kind}."
        raise FileNotFoundError(msg)


__all__ = ["EDAXPathHandler"]

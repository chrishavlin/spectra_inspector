from functools import lru_cache

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server.processor.derived_data import DerivedDataStore
from spectra_inspector_server.settings import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_database_session() -> EDAXPathHandler:
    S = get_settings()
    return EDAXPathHandler(
        data_root=S.data_root,
        # in desktop mode the data root can be huge, so the scan is deferred
        # until a client picks a working directory via /datasets-in-directory.
        init_db=not S.desktop_mode,
        allow_mixed_basenames=S.db_allow_mixed_basenames,
        # the cap only applies to the client-driven scans of desktop mode.
        max_datasets=S.max_datasets if S.desktop_mode else None,
    )


@lru_cache
def get_derived_data_store() -> DerivedDataStore | None:
    """The on-disk derived data store, or None when no directory is set."""
    S = get_settings()
    if S.derived_data_dir is None:
        return None
    return DerivedDataStore(
        S.derived_data_dir, S.data_root, write_on_miss=S.derived_write_on_miss
    )

from functools import lru_cache

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
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

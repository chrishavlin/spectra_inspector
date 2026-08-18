import dataclasses
import json
from typing import Any

from spectra_inspector.utilities.interface import SpectraInspectorServerInterface
from spectra_inspector.utilities.model import CombinedMetadata, sampleMetadata

USER_STORE_DIV_ID = "user-mem-store"


def sample_metadata_for_store(meta: sampleMetadata | None) -> dict[str, Any] | None:
    """Flatten a `sampleMetadata` response into the plain dict the store holds.

    Everything in the user store is round-tripped through JSON by `dcc.Store`,
    so the pydantic models the server interface returns cannot be put in it as
    they are.
    """
    if meta is None:
        return None
    return meta.model_dump()


@dataclasses.dataclass
class UserStore:
    selected_dataset: str = "none"
    metadata_json: str = ""
    # a `sampleMetadata` payload, kept as a dict because the store is JSON;
    # see `sample_metadata_for_store`.
    sample_metadata: dict[str, Any] | None = None
    # desktop mode only: the server-side working directory the user picked
    # (relative to the server's data root) and the datasets found in it. Both
    # stay None when the server scans its whole data root at startup.
    working_directory: str | None = None
    available_files: list[str] | None = None
    truncated: bool = False
    # whether that directory was scanned recursively, so a server worker that
    # has to catch up scans it the same way the user asked for.
    working_directory_recursive: bool = True

    def get_metadata(self) -> CombinedMetadata | None:
        if self.metadata_json != "":
            return CombinedMetadata(**json.loads(self.metadata_json))
        return None

    def directory_sync(self) -> dict[str, Any]:
        """The working directory to pin backend requests to, as request params.

        Desktop mode's working directory lives in one server worker's memory,
        so behind several workers this store is the only authoritative copy --
        sending it along lets whichever worker answers rescan if it has to. An
        empty dict before the user commits a directory, since "" legitimately
        means the data root.
        """
        if self.working_directory is None:
            return {}
        return {
            "working_directory": self.working_directory,
            "working_directory_recursive": self.working_directory_recursive,
        }

    def conditionally_fetch_metadata(self) -> CombinedMetadata | None:

        md = self.get_metadata()
        if md is None and self.selected_dataset != "none":
            sisi = SpectraInspectorServerInterface()
            md = sisi.get_combined_image_metadata(
                self.selected_dataset, directory_sync=self.directory_sync()
            )

        return md


def updateDataStore(data: dict, key: str, value: Any) -> dict:
    us = UserStore(**data)
    setattr(us, key, value)
    return dataclasses.asdict(us)

import dataclasses
import json
from typing import Any

from spectra_inspector.server.model import CombinedMetadata
from spectra_inspector.utilities.interface import SpectraInspectorServerInterface

USER_STORE_DIV_ID = "user-mem-store"


@dataclasses.dataclass
class UserStore:
    selected_dataset: str = "none"
    metadata_json: str = ""

    def get_metadata(self) -> CombinedMetadata | None:
        if self.metadata_json != "":
            return CombinedMetadata(**json.loads(self.metadata_json))
        return None

    def conditionally_fetch_metadata(self) -> CombinedMetadata | None:

        md = self.get_metadata()
        if md is None and self.selected_dataset != "none":
            sisi = SpectraInspectorServerInterface()
            md = sisi.get_combined_image_metadata(self.selected_dataset)

        return md


def updateDataStore(data: dict, key: str, value: Any) -> dict:
    us = UserStore(**data)
    setattr(us, key, value)
    return dataclasses.asdict(us)

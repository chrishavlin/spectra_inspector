import dataclasses
import json
from typing import Any

from spectra_inspector.utilities.model import CombinedMetadata

USER_STORE_DIV_ID = "user-mem-store"


@dataclasses.dataclass
class UserStore:
    selected_dataset: str = "none"
    metadata_json: str = ""

    def get_metadata(self) -> CombinedMetadata | None:
        if self.metadata_json != "":
            return CombinedMetadata(**json.loads(self.metadata_json))
        return None


def updateDataStore(data: dict, key: str, value: Any) -> dict:
    us = UserStore(**data)
    setattr(us, key, value)
    return dataclasses.asdict(us)

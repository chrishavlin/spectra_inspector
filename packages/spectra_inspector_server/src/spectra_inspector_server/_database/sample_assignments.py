"""The optional ``sample_assignments.yaml``: which sample a map belongs to.

An override on top of the filename heuristic (``_map_to_sample_name``), for maps
whose name does not reduce to a ``sample_metadata.csv`` sample id::

    schema: 1
    maps:
      "session-a/whatever-my-name-is.spd":
        sample: C-16
        note: "optional free text"

Keys are the file's path relative to the data root, whatever the database keys
its entries by, so a file reads the same with and without mixed-basename mode.
They are compared after ``normalize_key``, which makes a file written on one
platform match on another. An entry for a ``.spd`` also covers the ``.spc`` next
to it; see ``OnDiskDatabase.available_samples``.

Fields this version does not know are ignored rather than rejected, so that a
file carrying the later provenance fields still loads. A file that cannot be
read is logged and treated as absent: it never fails a scan.
"""

import unicodedata
from pathlib import Path, PurePath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from spectra_inspector_server._logging import spectraLogger


class _Assignment(BaseModel):
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)

    sample: str
    note: str | None = None


class _AssignmentsFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[1] = Field(default=1, alias="schema")
    maps: dict[str, _Assignment] = Field(default_factory=dict)

    @field_validator("maps", mode="before")
    @classmethod
    def _empty_maps(cls, value: Any) -> Any:
        # a bare "maps:" line parses to None
        return {} if value is None else value


def normalize_key(key: str) -> str:
    """The form in which assignment keys and file paths are compared.

    "/"-separated with no leading slash, and NFC: macOS hands back decomposed
    filenames where the same name typed elsewhere is composed.
    """
    return unicodedata.normalize("NFC", key.replace("\\", "/")).lstrip("/")


def assignment_key(path: PurePath, data_root: Path) -> str | None:
    """The key ``path`` is looked up under, None when it is outside the root."""
    try:
        relative = path.relative_to(data_root)
    except ValueError:
        # a working directory arrives resolved, the data root as configured
        try:
            relative = Path(path).resolve().relative_to(data_root.resolve())
        except ValueError:
            return None
    return normalize_key(relative.as_posix())


def load_sample_assignments(path: Path) -> dict[str, str]:
    """Normalized key -> sample id for every entry of the file at ``path``."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        parsed = _AssignmentsFile.model_validate({} if raw is None else raw)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        if isinstance(exc, ValidationError):
            detail = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            )
        else:
            detail = str(exc)
        spectraLogger.warning(
            "Ignoring sample assignments file %s, could not read it: %s", path, detail
        )
        return {}

    assignments = {
        normalize_key(key): entry.sample for key, entry in parsed.maps.items()
    }
    spectraLogger.info("Loaded %d sample assignments from %s", len(assignments), path)
    return assignments

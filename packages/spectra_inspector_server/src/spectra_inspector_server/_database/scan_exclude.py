"""The optional ``scan_exclude.yaml``: files on disk that are not to be served.

Read from the data root only, and applied to every scan beneath it::

    schema: 1
    exclude:
      - "session-a"              # a directory and everything under it
      - "session-b/map123.*"     # one file set
      - "**/scratch"             # a directory name at any depth

A pattern is a path relative to the data root. ``*`` and ``?`` match within one
path segment, a ``**`` segment matches any number of directories, and every
other character is literal (no ``[...]`` classes, since brackets turn up in map
names). A pattern that matches a directory excludes the whole subtree. Paths are
compared after ``sample_assignments.normalize_key``, case-sensitively.

Excluding a ``.spd`` also excludes the ``.spc`` beside it, as an assignment for
a ``.spd`` covers that ``.spc``; otherwise the map would linger as a
spectrum-only dataset.

Nothing is moved or touched, so the derived data of an excluded map stays valid
and is picked up again once the pattern is removed. A file that cannot be read
is logged and treated as absent: it never fails a scan.
"""

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from spectra_inspector_server._database.sample_assignments import (
    assignment_key,
    normalize_key,
)
from spectra_inspector_server._logging import spectraLogger

SCAN_EXCLUDE_YAML = "scan_exclude.yaml"


class _ExcludeFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[1] = Field(default=1, alias="schema")
    exclude: list[str] = Field(default_factory=list)

    @field_validator("exclude", mode="before")
    @classmethod
    def _empty_exclude(cls, value: Any) -> Any:
        # a bare "exclude:" line parses to None
        return [] if value is None else value


def _segment_regex(segment: str) -> str:
    out = ""
    for char in segment:
        if char == "*":
            out += "[^/]*"
        elif char == "?":
            out += "[^/]"
        else:
            out += re.escape(char)
    return out


def _pattern_regex(pattern: str) -> re.Pattern[str] | None:
    segments = [s for s in normalize_key(pattern.strip()).split("/") if s]
    if not segments:
        return None
    regex = ""
    for i, segment in enumerate(segments):
        last = i == len(segments) - 1
        if segment == "**":
            regex += "[^/]+(?:/[^/]+)*" if last else "(?:[^/]+/)*"
        else:
            regex += _segment_regex(segment) + ("" if last else "/")
    return re.compile(regex)


class ScanExclusions:
    """The patterns of one ``scan_exclude.yaml``, relative to ``data_root``."""

    def __init__(self, data_root: Path, patterns: list[str] | None = None) -> None:
        self.data_root = data_root
        self.patterns = list(patterns or [])
        self._regexes = [
            regex
            for pattern in self.patterns
            if (regex := _pattern_regex(pattern)) is not None
        ]

    def __bool__(self) -> bool:
        return bool(self._regexes)

    def excludes(self, path: Path) -> bool:
        """Whether ``path``, or a directory above it, matches a pattern."""
        if not self._regexes:
            return False
        if self._key_excluded(assignment_key(path, self.data_root)):
            return True
        if path.suffix == ".spc":
            return self._key_excluded(
                assignment_key(path.with_suffix(".spd"), self.data_root)
            )
        return False

    def filter_inventory(self, files: dict[str, list[Path]]) -> dict[str, list[Path]]:
        """A directory inventory (extension -> paths) without the excluded files."""
        return {
            ext: [p for p in paths if not self.excludes(p)]
            for ext, paths in files.items()
        }

    def _key_excluded(self, key: str | None) -> bool:
        if key is None or key in ("", "."):
            return False
        segments = key.split("/")
        return any(
            regex.fullmatch("/".join(segments[:depth]))
            for depth in range(1, len(segments) + 1)
            for regex in self._regexes
        )


def load_scan_exclusions(data_root: Path) -> ScanExclusions:
    """The exclusions of ``data_root``, empty when it has no exclude file."""
    path = data_root / SCAN_EXCLUDE_YAML
    if not path.is_file():
        return ScanExclusions(data_root)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        parsed = _ExcludeFile.model_validate({} if raw is None else raw)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        if isinstance(exc, ValidationError):
            detail = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            )
        else:
            detail = str(exc)
        spectraLogger.warning(
            "Ignoring scan exclude file %s, could not read it: %s", path, detail
        )
        return ScanExclusions(data_root)

    exclusions = ScanExclusions(data_root, parsed.exclude)
    spectraLogger.info(
        "Loaded %d scan exclude patterns from %s", len(exclusions.patterns), path
    )
    return exclusions

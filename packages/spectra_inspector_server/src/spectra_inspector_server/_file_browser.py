"""Read-only browsing of the directory tree beneath the configured data root.

Used by the desktop-mode endpoints so a client can pick the working directory to
scan instead of paying for a full recursive scan of the data root at startup.
Every path that arrives from a client goes through ``resolve_within_root``, which
is the only thing keeping the browsing confined to the data root.
"""

from pathlib import Path

from spectra_inspector_server._database.on_disk_db import (
    _check_files_in_directory,
    _inventory_directory,
    find_spc_files,
)
from spectra_inspector_server.model import directoryEntry, directoryListing


class PathOutsideRootError(ValueError):
    """Raised when a requested path resolves outside of the data root."""


def resolve_within_root(data_root: str | Path, path: str | None = None) -> Path:
    """Resolve a client-supplied path against the data root.

    Both relative and absolute paths are accepted, but the result must be the
    data root itself or a descendant of it. Symlinks are resolved before the
    check, so a symlink pointing out of the tree is rejected too.
    """

    root = Path(data_root).resolve()

    raw = (path or "").strip()
    if raw in ("", ".", "/"):
        return root

    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()

    if resolved != root and root not in resolved.parents:
        msg = f"'{raw}' is outside of the data root"
        raise PathOutsideRootError(msg)

    return resolved


def relative_to_root(data_root: str | Path, path: Path) -> str:
    """The wire representation of ``path``: posix, relative to the data root."""
    root = Path(data_root).resolve()
    if path == root:
        return ""
    return path.relative_to(root).as_posix()


def list_directory(
    data_root: str | Path,
    path: str | None = None,
    allow_mixed_basenames: bool = False,
) -> directoryListing:
    """List the subdirectories of one directory within the data root.

    Raises
    ------
    PathOutsideRootError
        if ``path`` resolves outside of ``data_root``.
    NotADirectoryError
        if the resolved path is not an existing directory.
    OSError
        if the directory cannot be read.

    """

    root = Path(data_root).resolve()
    target = resolve_within_root(root, path)

    if not target.is_dir():
        msg = f"'{path}' is not a directory"
        raise NotADirectoryError(msg)

    files, subdirs = _inventory_directory(target)

    entries = [
        directoryEntry(name=d.name, path=relative_to_root(root, d))
        for d in sorted(subdirs, key=lambda p: p.name.lower())
        if not d.name.startswith(".")
    ]

    datasets = _check_files_in_directory(
        target,
        allow_mixed_basenames=allow_mixed_basenames,
        inventoried_files=files,
    )

    parent_path: str | None = None
    if target != root:
        parent_path = relative_to_root(root, target.parent)

    return directoryListing(
        path=relative_to_root(root, target),
        name=target.name,
        parent_path=parent_path,
        directories=entries,
        dataset_count=len(datasets),
        spectrum_count=len(find_spc_files(target, inventoried_files=files)),
    )


__all__ = [
    "PathOutsideRootError",
    "list_directory",
    "relative_to_root",
    "resolve_within_root",
]

"""An on-disk store of data derived from the raw cubes, one ``.npz`` per
entry.

The first thing every user does with a sample is load its full spectrum and
the full-extent images of a few element windows. Each is a pass over the whole
cube and, cold off disk, many seconds; several users hitting the same handful
of samples recompute identical results. Zoom and pan never reach the server,
so serving full-extent results from here covers nearly all of that load.
Subset selections (a box or a polygon) bypass the store entirely. The entries
are rebuildable but not disposable: the UI is only quick while they exist,
and the store is where any further derived product (downsampled cubes, say)
belongs.

An entry is keyed by the fileset's path relative to the data root (not its
basename, which the scan has to special-case for duplicates), the op name, the
exact arguments and the ``.spd`` stamp ``(mtime_ns, size)`` that
``file_loaders._file_stamp`` computes. Only an exact match is a hit: a stamp
mismatch, a missing file or any failure to read an entry (corrupt, partial,
wrong shape, unreadable) is a miss, logged and never raised. The store can
only ever make a request faster, not fail it.

The directory mirrors the data tree: the entries for
``<data_root>/a/b/map123_0.spd`` live under ``<derived_dir>/a/b/map123_0/``,
named from the op and its arguments. Each ``.npz`` holds the array plus a JSON
string of its key. Writes go to a temporary name and are renamed into place so
a reader never sees a half-written entry, and nothing here ever deletes an
entry. Whether the server writes an entry it had to compute is the
``write_on_miss`` flag (``SPECTRA_INSPECTOR_DERIVED_WRITE_ON_MISS``); a
directory that turns out not to be writable just means no writes either.

``scripts/precompute_derived_data.py`` fills the store ahead of time with the
entries the frontend's default view asks for; ``channel_range_for_window``
converts the element windows to channel ranges by the frontend's own rule, so
the script's entries are the ones the handler then hits.
"""

import json
import os
import uuid
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.model import EDAX_axis, EDAX_file_set
from spectra_inspector_server.processor.file_loaders import _file_stamp

# the element panels the frontend opens on (its ``_INITIAL_PANEL_ELEMENTS``)
DEFAULT_PRECOMPUTE_ELEMENTS: tuple[str, ...] = ("Mg", "Al", "Si")

OP_IMAGE = "image"
OP_SPECTRUM = "spectrum"

_ARRAY_FIELD = "array"
_KEY_FIELD = "key"


def channel_range_for_window(
    channel_axis: EDAX_axis, window_keV: tuple[float, float]
) -> tuple[int, int]:
    """The ``(start, stop)`` channel range the frontend asks for when a panel
    shows ``window_keV``: each bound rounded to its closest channel, as
    ``spectra_inspector.utilities.scaling.get_closest_index`` does. A test
    pins the two to the same answer; if they drift, the precomputed entries
    simply miss."""
    return (
        _closest_index(channel_axis, window_keV[0]),
        _closest_index(channel_axis, window_keV[1]),
    )


def _closest_index(ax: EDAX_axis, value: float) -> int:
    return int(np.round((value - ax.offset) / ax.scale))


def _entry_name(op: str, args: dict[str, Any]) -> str:
    parts = [op]
    for name in sorted(args):
        value = args[name]
        if value is None:
            continue
        if isinstance(value, list | tuple):
            parts.append("-".join(str(v) for v in value))
        else:
            parts.append(str(value))
    return "_".join(parts) + ".npz"


class DerivedDataStore:
    """Full-extent results of the reductions in ``operations.py``, on disk.

    Parameters
    ----------
    derived_dir : Path
        the directory holding the entries, laid out as the data tree is
    data_root : Path
        the data root the filesets' relative paths are taken against
    write_on_miss : bool, optional
        whether :meth:`store` writes anything, by default True. False makes
        the store read-only for this process.
    """

    def __init__(
        self, derived_dir: str | Path, data_root: str | Path, write_on_miss: bool = True
    ) -> None:
        self.derived_dir = Path(derived_dir)
        self.data_root = Path(data_root)
        self.write_on_miss = write_on_miss

    def entry_path(self, fileset: EDAX_file_set, op: str, args: dict[str, Any]) -> Path:
        """Where the entry for ``op`` with ``args`` on ``fileset`` lives,
        whether or not it exists.

        Raises
        ------
        ValueError
            If the fileset is not under the data root.
        """
        return self._entry_dir(fileset) / _entry_name(op, args)

    def _entry_dir(self, fileset: EDAX_file_set) -> Path:
        return self.derived_dir / self._relative_path(fileset).with_suffix("")

    def _relative_path(self, fileset: EDAX_file_set) -> Path:
        return Path(fileset.spd).resolve().relative_to(self.data_root.resolve())

    def _key(
        self, fileset: EDAX_file_set, op: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "fileset": self._relative_path(fileset).as_posix(),
            "op": op,
            "args": _normalized(args),
            "stamp": list(_file_stamp(Path(fileset.spd))),
        }

    def has_entry(self, fileset: EDAX_file_set, op: str, args: dict[str, Any]) -> bool:
        """Whether a matching entry exists, checked by its key alone without
        reading the array."""
        try:
            path = self.entry_path(fileset, op, args)
            expected = self._key(fileset, op, args)
            with path.open("rb") as f, np.load(f, allow_pickle=False) as entry:
                return bool(_read_key(entry) == expected)
        except _MISS_ERRORS:
            return False

    def lookup(
        self,
        fileset: EDAX_file_set,
        op: str,
        args: dict[str, Any],
        expected_shape: tuple[int, ...],
    ) -> npt.NDArray[np.int64] | None:
        """The stored array for ``op`` with ``args`` on ``fileset``, or None
        on a miss. An entry whose key or shape does not match, or that cannot
        be read at all, is a miss and is logged rather than raised."""
        path: Path | None = None
        try:
            path = self.entry_path(fileset, op, args)
            if not path.is_file():
                return None
            expected = self._key(fileset, op, args)
            # opened here rather than by np.load, which leaks the handle when
            # the file turns out not to be an archive
            with path.open("rb") as f, np.load(f, allow_pickle=False) as entry:
                if _read_key(entry) != expected:
                    spectraLogger.debug("derived data: stale entry %s", path)
                    return None
                array = np.asarray(entry[_ARRAY_FIELD])
        except _MISS_ERRORS:
            spectraLogger.warning(
                "derived data: could not read %s, recomputing", path, exc_info=True
            )
            return None

        if array.shape != tuple(expected_shape) or not np.issubdtype(
            array.dtype, np.integer
        ):
            spectraLogger.warning(
                "derived data: entry %s has shape %s and dtype %s, expected shape "
                "%s, recomputing",
                path,
                array.shape,
                array.dtype,
                expected_shape,
            )
            return None
        spectraLogger.debug("derived data: served %s from %s", op, path)
        return array.astype(np.int64, copy=False)

    def store(
        self,
        fileset: EDAX_file_set,
        op: str,
        args: dict[str, Any],
        array: npt.NDArray[np.int64],
    ) -> bool:
        """Write ``array`` as the entry for ``op`` with ``args`` on ``fileset``,
        replacing any existing one. Returns False without writing when
        ``write_on_miss`` is off, and after logging when the directory cannot
        be written to."""
        if not self.write_on_miss:
            return False
        tmp: Path | None = None
        try:
            path = self.entry_path(fileset, op, args)
            key = json.dumps(self._key(fileset, op, args), sort_keys=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
            with tmp.open("wb") as f:
                np.savez(f, array=array, key=np.array(key))
            tmp.replace(path)
        except (OSError, ValueError):
            spectraLogger.warning(
                "derived data: could not write an entry for %s",
                fileset.spd,
                exc_info=True,
            )
            if tmp is not None:
                tmp.unlink(missing_ok=True)
            return False
        return True


_MISS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    EOFError,
    zipfile.BadZipFile,
    json.JSONDecodeError,
    UnicodeDecodeError,
)


def _read_key(entry: Any) -> Any:
    raw = entry[_KEY_FIELD]
    if raw.dtype.kind != "U" or raw.shape != ():
        msg = "the key is not a string"
        raise ValueError(msg)
    return json.loads(str(raw.item()))


def _normalized(args: dict[str, Any]) -> dict[str, Any]:
    """``args`` as they round-trip through JSON, so a tuple compares equal to
    the list it is read back as."""
    normalized: dict[str, Any] = json.loads(json.dumps(args, sort_keys=True))
    return normalized


__all__ = [
    "DEFAULT_PRECOMPUTE_ELEMENTS",
    "OP_IMAGE",
    "OP_SPECTRUM",
    "DerivedDataStore",
    "channel_range_for_window",
]

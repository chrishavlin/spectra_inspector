"""Fill the server's on-disk derived data store ahead of the first request.

The store (``processor/derived_data.py``) holds the full-extent results that
the frontend's default view asks for: the whole-map spectrum and the summed
image of each default element window. This script writes those entries for
every map under a data root, reading each cube once for everything it is
missing (``OperationEDAXStateHandler.get_spectrum_and_images``), so the first
user of a sample waits on none of them.

Run it from the server package so that the server is importable::

    cd packages/spectra_inspector_server
    uv run python ../../scripts/precompute_derived_data.py [DATA_ROOT [DERIVED_DIR]]

Either path left out is taken from the server's settings, that is the
environment and the ``.env`` in the current directory
(``SPECTRA_INSPECTOR_DATA_ROOT``, ``SPECTRA_INSPECTOR_DERIVED_DATA_DIR``), so
with no arguments the script fills the store of the deployment it is run
from. The tree is walked with the same scan the server uses, so the scan has
to agree with the deployment on ``SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES``:
it decides which filesets exist. The setting carries over whenever the
settings are read, and ``--allow-mixed-basenames`` turns it on regardless.
``--elements`` overrides the element windows. Entries whose stamp
already matches are skipped, so re-running after adding data is cheap, and the
script only ever adds entries, so it is safe against a live server.
``--overwrite`` instead empties the derived data directory first, so every
entry is recomputed; that is not safe against a live server, and the script
refuses to empty a directory that is, contains or lies inside the data root.
The directory itself is kept, with its ownership.

``--workers N`` spreads the filesets over a pool of N processes, one fileset
per task; the pass over any one cube stays serial. The default of one is the
right choice for a spinning disk, where a second reader only makes the head
seek. On an SSD each extra worker adds a core's worth of summing until the
drive or memory bandwidth saturates, so a few workers pay off there. Entries
are written through a temporary name and renamed, so workers never collide.

The directory mirrors the data tree and the entries are keyed on the ``.spd``
files' modification time and size, so a store built elsewhere can be rsynced
next to the data (``rsync -a`` preserves the mtime).
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from spectra_inspector_server.model import EDAX_file_set

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.calibration import element_energy_ranges_keV
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler
from spectra_inspector_server.processor.derived_data import (
    DEFAULT_PRECOMPUTE_ELEMENTS,
    OP_IMAGE,
    OP_SPECTRUM,
    DerivedDataStore,
    channel_range_for_window,
)
from spectra_inspector_server.settings import ENV_PREFIX, Settings


@dataclass
class Report:
    hits: int = 0
    writes: int = 0
    skipped_filesets: int = 0

    def summary(self) -> str:
        return (
            f"{self.hits} entries already up to date, {self.writes} written, "
            f"{self.skipped_filesets} filesets skipped"
        )

    def add(self, other: Report) -> None:
        self.hits += other.hits
        self.writes += other.writes
        self.skipped_filesets += other.skipped_filesets


def precompute(
    data_root: Path,
    derived_dir: Path,
    elements: tuple[str, ...] = DEFAULT_PRECOMPUTE_ELEMENTS,
    allow_mixed_basenames: bool = False,
    workers: int = 1,
    mp_context: multiprocessing.context.BaseContext | None = None,
    overwrite: bool = False,
) -> Report:
    """Write the default-view entries for every map under ``data_root``,
    over ``workers`` processes when more than one. ``mp_context`` picks the
    pool's start method; the tests pass a fork context so their patched
    loaders reach the workers. ``overwrite`` empties ``derived_dir`` first."""
    unknown = sorted(set(elements) - element_energy_ranges_keV.keys())
    if unknown:
        msg = f"no energy window for {unknown}; known: {sorted(element_energy_ranges_keV)}"
        raise ValueError(msg)
    if workers < 1:
        msg = f"workers must be at least 1, got {workers}"
        raise ValueError(msg)
    if overwrite:
        empty_derived_dir(derived_dir, data_root)

    ph = EDAXPathHandler(
        data_root, init_db=True, allow_mixed_basenames=allow_mixed_basenames
    )
    filesets = [
        (name, ph.database.available_maps[name])
        for name in sorted(ph.database.available_maps)
    ]
    report = Report()

    if workers == 1:
        store = DerivedDataStore(derived_dir, data_root)
        ops = OperationEDAXStateHandler(ph, derived_data=store)
        for name, fileset in filesets:
            report.add(_precompute_one(ops, store, name, fileset, elements))
        return report

    with ProcessPoolExecutor(
        max_workers=min(workers, max(len(filesets), 1)),
        mp_context=mp_context,
        initializer=_init_worker,
        initargs=(data_root, derived_dir, spectraLogger.getEffectiveLevel()),
    ) as pool:
        for partial in pool.map(
            _precompute_in_worker,
            [(name, fileset, elements) for name, fileset in filesets],
        ):
            report.add(partial)
    return report


def empty_derived_dir(derived_dir: Path, data_root: Path) -> None:
    """Delete everything inside ``derived_dir``, keeping the directory.

    Raises
    ------
    ValueError
        If ``derived_dir`` is the data root, lies inside it or contains it.
    """
    derived = derived_dir.resolve()
    root = data_root.resolve()
    if derived == root or derived in root.parents or root in derived.parents:
        msg = f"refusing to empty {derived_dir}: it is, contains or is inside the data root {data_root}"
        raise ValueError(msg)
    if not derived.is_dir():
        return
    entries = list(derived.iterdir())
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    spectraLogger.info("emptied %s (%d entries removed)", derived_dir, len(entries))


def _precompute_one(
    ops: OperationEDAXStateHandler,
    store: DerivedDataStore,
    name: str,
    fileset: EDAX_file_set,
    elements: tuple[str, ...],
) -> Report:
    """The entries for one fileset, with any failure logged and counted as
    a skipped fileset rather than raised."""
    report = Report()
    try:
        _precompute_fileset(ops, store, name, elements, report)
    except Exception:  # noqa: BLE001
        spectraLogger.warning("skipping %s", fileset.spd, exc_info=True)
        report.skipped_filesets += 1
    return report


# this worker process's handler and store, built once by _init_worker: a
# path handler with no scan of its own, handed each fileset with its task
_worker: tuple[OperationEDAXStateHandler, DerivedDataStore] | None = None


def _init_worker(data_root: Path, derived_dir: Path, log_level: int) -> None:
    global _worker  # noqa: PLW0603
    spectraLogger.setLevel(log_level)
    store = DerivedDataStore(derived_dir, data_root)
    ops = OperationEDAXStateHandler(
        EDAXPathHandler(data_root, init_db=False), derived_data=store
    )
    _worker = (ops, store)


def _precompute_in_worker(
    task: tuple[str, EDAX_file_set, tuple[str, ...]],
) -> Report:
    name, fileset, elements = task
    assert _worker is not None
    ops, store = _worker
    ops.ph.database.add_fileset(name, fileset)
    return _precompute_one(ops, store, name, fileset, elements)


def _precompute_fileset(
    ops: OperationEDAXStateHandler,
    store: DerivedDataStore,
    name: str,
    elements: tuple[str, ...],
    report: Report,
) -> None:
    fileset = ops.ph.database.available_maps[name]
    channel_axis = ops.get_sample_axes(name)[2]

    need_spectrum = not store.has_entry(fileset, OP_SPECTRUM, {"channel_range": None})
    report.hits += 0 if need_spectrum else 1

    # keyed by channel range so two elements with one window are one image
    missing: dict[tuple[int, int], str] = {}
    for element in elements:
        channel_range = channel_range_for_window(
            channel_axis, element_energy_ranges_keV[element]
        )
        if store.has_entry(fileset, OP_IMAGE, {"channel_range": list(channel_range)}):
            report.hits += 1
        else:
            missing[channel_range] = element

    if not need_spectrum and not missing:
        return

    wanted = (["spectrum"] if need_spectrum else []) + [
        f"{element} image {channel_range}" for channel_range, element in missing.items()
    ]
    spectraLogger.info("%s: %s in one pass", fileset.spd, ", ".join(wanted))
    ops.get_spectrum_and_images(name, list(missing), include_spectrum=need_spectrum)
    report.writes += int(need_spectrum) + len(missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_root",
        type=Path,
        nargs="?",
        help=f"the server's data root (default: {ENV_PREFIX}DATA_ROOT)",
    )
    parser.add_argument(
        "derived_dir",
        type=Path,
        nargs="?",
        help=f"the derived data directory (default: {ENV_PREFIX}DERIVED_DATA_DIR)",
    )
    parser.add_argument(
        "--elements",
        nargs="+",
        default=list(DEFAULT_PRECOMPUTE_ELEMENTS),
        metavar="EL",
        help=f"element windows to image (default: {' '.join(DEFAULT_PRECOMPUTE_ELEMENTS)})",
    )
    parser.add_argument(
        "--allow-mixed-basenames",
        action="store_true",
        help="scan as SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES=true does",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="filesets to process at once (default: 1; more pays off on an SSD)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="empty the derived data directory first, recomputing every entry",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    spectraLogger.setLevel(args.log_level.upper())
    logging.getLogger().setLevel(args.log_level.upper())

    data_root: Path | None = args.data_root
    derived_dir: Path | None = args.derived_dir
    allow_mixed_basenames: bool = args.allow_mixed_basenames
    if data_root is None or derived_dir is None:
        settings = Settings()
        if data_root is None:
            data_root = Path(settings.data_root)
        if derived_dir is None:
            if settings.derived_data_dir is None:
                parser.error(
                    f"no derived data directory given and {ENV_PREFIX}DERIVED_DATA_DIR is unset"
                )
            derived_dir = Path(settings.derived_data_dir)
        allow_mixed_basenames = (
            allow_mixed_basenames or settings.db_allow_mixed_basenames
        )

    if not data_root.is_dir():
        parser.error(f"data root is not a directory: {data_root}")
    if args.workers < 1:
        parser.error(f"--workers must be at least 1, got {args.workers}")

    report = precompute(
        data_root,
        derived_dir,
        elements=tuple(args.elements),
        allow_mixed_basenames=allow_mixed_basenames,
        workers=args.workers,
        overwrite=args.overwrite,
    )
    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())

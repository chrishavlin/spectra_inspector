"""Build the spectral block pyramid of every map under a data root.

A pyramid (``processor/pyramid.py``) is the cube summed over square blocks of
the map at a few block sizes, stored as an OME-Zarr group in the derived data
directory next to the map's other entries. With one in place the server
answers box and polygon spectra from block sums plus the raw pixels along the
selection's edge, instead of reading every selected pixel's spectrum. This
script walks the data root with the server's own scan and builds the pyramid
of every map that has none, or whose pyramid was built from an older ``.spd``
or to a different layout.

Run it from the server package so that the server is importable::

    cd packages/spectra_inspector_server
    uv run python ../../scripts/build_spectral_pyramids.py [DATA_ROOT [DERIVED_DIR]]

Either path left out is taken from the server's settings, that is the
environment and the ``.env`` in the current directory
(``SPECTRA_INSPECTOR_DATA_ROOT``, ``SPECTRA_INSPECTOR_DERIVED_DATA_DIR``).
The scan has to agree with the deployment on
``SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES``, which carries over whenever
the settings are read; ``--allow-mixed-basenames`` turns it on regardless.

``--block-sizes`` sets the layout: the block edge of each level in pixels,
finest first, each a multiple of the one before. The number of values is the
number of levels and the ratio of neighbours the refinement factor, so
``--block-sizes 4 16 64`` (the default) is three levels refined by four each
time. A level costs the cube's size divided by the block area, so the finest
level sets the disk cost: 1/16 of the cube at 4 x 4 before compression.
``--samples`` restricts the run to the named maps.

Each pyramid is one pass over its cube, a slab of rows at a time, and is
built in a temporary directory that is renamed into place, so the script is
safe against a live server and against being interrupted. Up-to-date
pyramids are skipped, so re-running after adding data is cheap;
``--overwrite`` rebuilds them too. ``--workers N`` builds N maps at once,
which pays off on an SSD and hurts on a spinning disk.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.model import EDAX_file_set
from spectra_inspector_server.processor.derived_data import DerivedDataStore
from spectra_inspector_server.processor.file_loaders import load_edax_spd
from spectra_inspector_server.processor.pyramid import (
    DEFAULT_BLOCK_SIZES,
    PyramidSpec,
)
from spectra_inspector_server.settings import ENV_PREFIX, Settings


@dataclass
class Report:
    up_to_date: int = 0
    built: int = 0
    skipped_filesets: int = 0

    def summary(self) -> str:
        return (
            f"{self.up_to_date} pyramids already up to date, {self.built} built, "
            f"{self.skipped_filesets} filesets skipped"
        )

    def add(self, other: Report) -> None:
        self.up_to_date += other.up_to_date
        self.built += other.built
        self.skipped_filesets += other.skipped_filesets


def build_pyramids(
    data_root: Path,
    derived_dir: Path,
    spec: PyramidSpec = PyramidSpec(),
    allow_mixed_basenames: bool = False,
    samples: tuple[str, ...] | None = None,
    workers: int = 1,
    mp_context: multiprocessing.context.BaseContext | None = None,
    overwrite: bool = False,
) -> Report:
    """Build the pyramid of every map under ``data_root`` into
    ``derived_dir``, over ``workers`` processes when more than one.
    ``samples`` restricts the run to those map names; ``overwrite`` rebuilds
    pyramids that are already up to date. ``mp_context`` picks the pool's
    start method; the tests pass a fork context so their patched loaders
    reach the workers."""
    if workers < 1:
        msg = f"workers must be at least 1, got {workers}"
        raise ValueError(msg)

    ph = EDAXPathHandler(
        data_root, init_db=True, allow_mixed_basenames=allow_mixed_basenames
    )
    names = sorted(ph.database.available_maps)
    if samples is not None:
        unknown = sorted(set(samples) - set(names))
        if unknown:
            msg = f"no such maps under {data_root}: {unknown}"
            raise ValueError(msg)
        names = [name for name in names if name in samples]
    filesets = [(name, ph.database.available_maps[name]) for name in names]
    report = Report()

    if workers == 1:
        store = DerivedDataStore(derived_dir, data_root)
        for _name, fileset in filesets:
            report.add(_build_one(store, fileset, spec, overwrite))
        return report

    with ProcessPoolExecutor(
        max_workers=min(workers, max(len(filesets), 1)),
        mp_context=mp_context,
        initializer=_init_worker,
        initargs=(data_root, derived_dir, spectraLogger.getEffectiveLevel()),
    ) as pool:
        for partial in pool.map(
            _build_in_worker,
            [(fileset, spec, overwrite) for _name, fileset in filesets],
        ):
            report.add(partial)
    return report


def _build_one(
    store: DerivedDataStore,
    fileset: EDAX_file_set,
    spec: PyramidSpec,
    overwrite: bool,
) -> Report:
    """The pyramid of one fileset, with any failure logged and counted as a
    skipped fileset rather than raised."""
    report = Report()
    try:
        if not overwrite and store.has_pyramid(fileset, spec):
            report.up_to_date += 1
            return report
        spectraLogger.info(
            "%s: building a pyramid with block sizes %s", fileset.spd, spec.block_sizes
        )
        data = load_edax_spd(fileset).data
        if data is None:
            msg = f"no data behind {fileset.spd}"
            raise ValueError(msg)  # noqa: TRY301
        if not store.store_pyramid(fileset, data, spec):
            msg = f"the pyramid of {fileset.spd} could not be written"
            raise OSError(msg)  # noqa: TRY301
        report.built += 1
    except Exception:  # noqa: BLE001
        spectraLogger.warning("skipping %s", fileset.spd, exc_info=True)
        report.skipped_filesets += 1
    return report


# this worker process's store, built once by _init_worker
_worker_store: DerivedDataStore | None = None


def _init_worker(data_root: Path, derived_dir: Path, log_level: int) -> None:
    global _worker_store  # noqa: PLW0603
    spectraLogger.setLevel(log_level)
    _worker_store = DerivedDataStore(derived_dir, data_root)


def _build_in_worker(task: tuple[EDAX_file_set, PyramidSpec, bool]) -> Report:
    fileset, spec, overwrite = task
    assert _worker_store is not None
    return _build_one(_worker_store, fileset, spec, overwrite)


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
        "--block-sizes",
        type=int,
        nargs="+",
        default=list(DEFAULT_BLOCK_SIZES),
        metavar="B",
        help=(
            "block edge of each level in pixels, finest first, each a multiple "
            f"of the previous (default: {' '.join(map(str, DEFAULT_BLOCK_SIZES))})"
        ),
    )
    parser.add_argument(
        "--samples",
        nargs="+",
        metavar="NAME",
        help="only these maps (default: every map under the data root)",
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
        help="maps to build at once (default: 1; more pays off on an SSD)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="rebuild pyramids that are already up to date",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    spectraLogger.setLevel(args.log_level.upper())
    logging.getLogger().setLevel(args.log_level.upper())

    try:
        spec = PyramidSpec(block_sizes=tuple(args.block_sizes))
    except ValueError as err:
        parser.error(f"--block-sizes: {err}")

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

    try:
        report = build_pyramids(
            data_root,
            derived_dir,
            spec=spec,
            allow_mixed_basenames=allow_mixed_basenames,
            samples=None if args.samples is None else tuple(args.samples),
            workers=args.workers,
            overwrite=args.overwrite,
        )
    except ValueError as err:
        parser.error(str(err))
    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Fill the server's on-disk result cache ahead of the first request.

The cache (``processor/result_cache.py``) holds the full-extent results that
the frontend's default view asks for: the whole-map spectrum and the summed
image of each default element window. This script writes those entries for
every map under a data root, reading each cube once for everything it is
missing (``OperationEDAXStateHandler.get_spectrum_and_images``), so the first
user of a sample waits on none of them.

Run it from the server package so that the server is importable::

    cd packages/spectra_inspector_server
    uv run python ../../scripts/precompute_result_cache.py DATA_ROOT CACHE_DIR

The tree is walked with the same scan the server uses, so pass
``--allow-mixed-basenames`` when the deployment sets
``SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES=true``: it decides which filesets
exist. ``--elements`` overrides the element windows. Entries whose stamp
already matches are skipped, so re-running after adding data is cheap, and the
script only ever adds entries, so it is safe against a live server.

The cache directory mirrors the data tree and the entries are keyed on the
``.spd`` files' modification time and size, so a cache built elsewhere can be
rsynced next to the data (``rsync -a`` preserves the mtime).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.calibration import element_energy_ranges_keV
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler
from spectra_inspector_server.processor.result_cache import (
    DEFAULT_PRECOMPUTE_ELEMENTS,
    OP_IMAGE,
    OP_SPECTRUM,
    ResultCache,
    channel_range_for_window,
)


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


def precompute(
    data_root: Path,
    cache_dir: Path,
    elements: tuple[str, ...] = DEFAULT_PRECOMPUTE_ELEMENTS,
    allow_mixed_basenames: bool = False,
) -> Report:
    """Write the default-view entries for every map under ``data_root``."""
    unknown = sorted(set(elements) - element_energy_ranges_keV.keys())
    if unknown:
        msg = f"no energy window for {unknown}; known: {sorted(element_energy_ranges_keV)}"
        raise ValueError(msg)

    ph = EDAXPathHandler(
        data_root, init_db=True, allow_mixed_basenames=allow_mixed_basenames
    )
    cache = ResultCache(cache_dir, data_root)
    ops = OperationEDAXStateHandler(ph, result_cache=cache)
    report = Report()

    for name in sorted(ph.database.available_maps):
        fileset = ph.database.available_maps[name]
        try:
            _precompute_fileset(ops, cache, name, elements, report)
        except Exception:  # noqa: BLE001
            spectraLogger.warning("skipping %s", fileset.spd, exc_info=True)
            report.skipped_filesets += 1
    return report


def _precompute_fileset(
    ops: OperationEDAXStateHandler,
    cache: ResultCache,
    name: str,
    elements: tuple[str, ...],
    report: Report,
) -> None:
    fileset = ops.ph.database.available_maps[name]
    channel_axis = ops.get_sample_axes(name)[2]

    need_spectrum = not cache.has_entry(fileset, OP_SPECTRUM, {"channel_range": None})
    report.hits += 0 if need_spectrum else 1

    # keyed by channel range so two elements with one window are one image
    missing: dict[tuple[int, int], str] = {}
    for element in elements:
        channel_range = channel_range_for_window(
            channel_axis, element_energy_ranges_keV[element]
        )
        if cache.has_entry(fileset, OP_IMAGE, {"channel_range": list(channel_range)}):
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
    parser.add_argument("data_root", type=Path, help="the server's data root")
    parser.add_argument("cache_dir", type=Path, help="the result cache directory")
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
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    spectraLogger.setLevel(args.log_level.upper())
    logging.getLogger().setLevel(args.log_level.upper())

    if not args.data_root.is_dir():
        parser.error(f"data root is not a directory: {args.data_root}")

    report = precompute(
        args.data_root,
        args.cache_dir,
        elements=tuple(args.elements),
        allow_mixed_basenames=args.allow_mixed_basenames,
    )
    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())

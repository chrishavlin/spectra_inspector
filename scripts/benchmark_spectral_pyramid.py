"""Time a map's region spectra with and without its spectral block pyramid.

For a box and a polygon on one map, the spectrum is computed the way
``get_spectrum`` does it off the raw cube and then again from the pyramid in
the derived data directory (``scripts/build_spectral_pyramids.py`` builds
one), each in a fresh process so that the peak resident set size is that
request's alone. The two answers are checked to be identical. A third run
sums the pyramid's blocks alone (``blocks_only``), never touching the cube,
and reports how far that approximation is from the exact spectrum. The table
gives the shortfall in total counts and the shape error, half the L1 distance
between the two spectra after each is normalised to unit area (0 is the same
shape, 1 is no overlap). Below it, the error per energy bin: the difference
``blocks - exact`` in counts and in counts per pixel (the blocks sum covers
fewer pixels, so per pixel is the fair comparison), each as its root mean
square over the bins, its largest value and where, and its mean with the
standard error of that mean; the same difference in units of the exact
spectrum's Poisson noise ``sqrt(counts)`` per bin, which says whether the
approximation is visible above counting statistics; and both again after the
exact spectrum is scaled to the pixel count the blocks cover, which separates
the missing area (a scale factor) from the boundary ring having a different
composition from the interior. ``--save-errors FILE``
writes every bin to a CSV for plotting. The cube is whatever the page cache
holds: run once to warm it, or drop the cache first (``sudo purge`` on macOS,
``echo 3 > /proc/sys/vm/drop_caches`` on Linux) for cold numbers.

Run it from the server package so that the server is importable::

    cd packages/spectra_inspector_server
    uv run python ../../scripts/benchmark_spectral_pyramid.py SAMPLE [DATA_ROOT [DERIVED_DIR]]

The paths default to the server's settings as the build script's do. The box
and polygon default to a quarter-map box and a blob in the middle of the map;
``--box R0 R1 C0 C1`` and ``--polygon R,C R,C ...`` set them.
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.processor._polygon import polygon_mask
from spectra_inspector_server.processor.derived_data import DerivedDataStore
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler
from spectra_inspector_server.settings import ENV_PREFIX, Settings

Vertex = tuple[float, float]


def _default_regions(
    shape: tuple[int, ...],
) -> tuple[tuple[int, int, int, int], list[Vertex]]:
    rows, cols = shape[0], shape[1]
    box = (rows // 4, 3 * rows // 4, cols // 4, 3 * cols // 4)
    # an irregular blob about half the map across
    centre = (rows / 2, cols / 2)
    radius = min(rows, cols) / 4
    angles = np.linspace(0, 2 * np.pi, 13, endpoint=False)
    wobble = 1 + 0.3 * np.sin(3 * angles)
    polygon = [
        (
            float(centre[0] + radius * w * np.sin(a)),
            float(centre[1] + radius * w * np.cos(a)),
        )
        for a, w in zip(angles, wobble, strict=True)
    ]
    return box, polygon


def _measure(
    data_root: Path,
    derived_dir: Path,
    sample: str,
    region: dict[str, object],
    method: str,
    repeat: int,
) -> dict[str, object]:
    """One region by one method (``raw``, ``pyramid`` or ``blocks``), in a
    child process: wall time of each repeat, the peak RSS and the result."""
    task = {
        "data_root": str(data_root),
        "derived_dir": str(derived_dir),
        "sample": sample,
        "region": region,
        "method": method,
        "repeat": repeat,
    }
    proc = subprocess.run(
        [sys.executable, __file__, "--child"],
        input=json.dumps(task),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode:
        sys.stderr.write(proc.stderr)
        msg = f"the child failed for {task}"
        raise RuntimeError(msg)
    result: dict[str, object] = json.loads(proc.stdout.strip().splitlines()[-1])
    return result


def _child() -> int:
    task = json.loads(sys.stdin.read())
    spectraLogger.setLevel("WARNING")
    data_root = Path(task["data_root"])
    store = DerivedDataStore(Path(task["derived_dir"]), data_root, write_on_miss=False)
    ops = OperationEDAXStateHandler(
        EDAXPathHandler(data_root, init_db=True), derived_data=store
    )
    region = task["region"]
    kwargs: dict[str, object] = {
        "use_pyramid": task["method"] != "raw",
        "blocks_only": task["method"] == "blocks",
    }
    if "box" in region:
        r0, r1, c0, c1 = region["box"]
        kwargs["index0_range"] = (r0, r1)
        kwargs["index1_range"] = (c0, c1)
    else:
        kwargs["polygon"] = [tuple(v) for v in region["polygon"]]

    # map the cube before timing, as the long-lived server worker has done
    ops.get_axis_sizes(task["sample"])
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    times = []
    intensity: list[int] = []
    for _ in range(task["repeat"]):
        start = time.perf_counter()
        spectrum = ops.get_spectrum(task["sample"], **kwargs)  # type: ignore[arg-type]
        times.append(time.perf_counter() - start)
        intensity = spectrum.intensity.tolist()
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024  # bytes on macOS, KiB on Linux

    # how many pixels the spectrum covers, for the per-pixel comparison
    shape = ops.get_axis_sizes(task["sample"])
    if "box" in region:
        mask, rows, cols = None, (r0, r1), (c0, c1)
        pixels = (r1 - r0) * (c1 - c0)
    else:
        mask, rows, cols = polygon_mask(kwargs["polygon"], (shape[0], shape[1]))  # type: ignore[arg-type]
        pixels = int(mask.sum())
    if task["method"] == "blocks":
        fileset = ops.ph.get_sample_edax_file_names(task["sample"])
        assert fileset is not None
        pyramid = store.load_pyramid(fileset)
        assert pyramid is not None
        cube = ops.ph.load_edax(task["sample"]).data
        assert cube is not None
        _, stats = pyramid.region_spectrum(
            cube, mask, rows, cols, (0, shape[2]), blocks_only=True
        )
        pixels = stats.summed_pixels

    print(
        json.dumps(
            {
                "times": times,
                "rss_before_MB": before * scale / 2**20,
                "rss_peak_MB": after * scale / 2**20,
                "intensity": intensity,
                "pixels": pixels,
            }
        )
    )
    return 0


def _approximation_error(exact: list[int], approx: list[int]) -> tuple[float, float]:
    """``(counts shortfall, shape error)`` of ``approx`` against ``exact``:
    the fraction of the total counts missing, and half the L1 distance
    between the two spectra normalised to unit area."""
    a = np.asarray(exact, dtype=np.float64)
    b = np.asarray(approx, dtype=np.float64)
    if a.sum() == 0:
        return 0.0, 0.0
    shortfall = 1 - b.sum() / a.sum()
    shape = 0.0 if b.sum() == 0 else 0.5 * np.abs(a / a.sum() - b / b.sum()).sum()
    return float(shortfall), float(shape)


def _per_bin_errors(
    exact: np.ndarray,
    approx: np.ndarray,
    exact_pixels: int,
    approx_pixels: int,
    energy_keV: np.ndarray,
) -> list[str]:
    """The lines describing ``approx - exact`` bin by bin."""
    n = len(exact)

    def describe(name: str, diff: np.ndarray, unit: str) -> str:
        worst = int(np.argmax(np.abs(diff)))
        rms = float(np.sqrt(np.mean(diff**2)))
        mean = float(diff.mean())
        standard_error = float(diff.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
        return (
            f"    {name:<14} rms {rms:.4g} {unit}, largest {diff[worst]:+.4g} {unit} "
            f"at {energy_keV[worst]:.3f} keV, mean {mean:+.4g} +/- {standard_error:.2g} (SE)"
        )

    counts = approx - exact
    per_pixel = approx / max(approx_pixels, 1) - exact / max(exact_pixels, 1)
    sigma = np.sqrt(np.maximum(exact, 1))
    in_sigma = counts / sigma
    # the exact spectrum scaled down to the pixels the blocks cover: what is
    # left is the boundary ring's composition, not the missing area
    rescaled = approx - exact * approx_pixels / max(exact_pixels, 1)
    rescaled_sigma = rescaled / sigma
    return [
        f"  blocks - exact per energy bin ({n} bins; {approx_pixels} of {exact_pixels} pixels summed):",
        describe("counts", counts, "counts"),
        describe("counts/pixel", per_pixel, "counts/px"),
        describe("vs Poisson", in_sigma, "sigma"),
        f"    bins beyond 1 sigma: {int((np.abs(in_sigma) > 1).sum())}, "
        f"beyond 3 sigma: {int((np.abs(in_sigma) > 3).sum())}",
        "  after scaling exact to the same pixel count:",
        describe("counts", rescaled, "counts"),
        describe("vs Poisson", rescaled_sigma, "sigma"),
        f"    bins beyond 1 sigma: {int((np.abs(rescaled_sigma) > 1).sum())}, "
        f"beyond 3 sigma: {int((np.abs(rescaled_sigma) > 3).sum())}",
    ]


def _save_errors(
    path: Path,
    label: str,
    energy_keV: np.ndarray,
    exact: np.ndarray,
    approx: np.ndarray,
    exact_pixels: int,
    approx_pixels: int,
) -> None:
    sigma = np.sqrt(np.maximum(exact, 1))
    table = np.column_stack(
        [
            np.arange(len(exact)),
            energy_keV,
            exact,
            approx,
            approx - exact,
            approx / max(approx_pixels, 1) - exact / max(exact_pixels, 1),
            (approx - exact) / sigma,
            (approx - exact * approx_pixels / max(exact_pixels, 1)) / sigma,
        ]
    )
    np.savetxt(
        path,
        table,
        delimiter=",",
        header=(
            f"{label}: exact over {exact_pixels} pixels, blocks over {approx_pixels}\n"
            "channel,energy_keV,exact_counts,blocks_counts,diff_counts,"
            "diff_counts_per_pixel,diff_in_poisson_sigma,"
            "diff_after_pixel_scaling_in_poisson_sigma"
        ),
        fmt=["%d", "%.6f", "%d", "%d", "%d", "%.8g", "%.6g", "%.6g"],
    )


def main(argv: list[str] | None = None) -> int:
    if argv is None and "--child" in sys.argv[1:]:
        return _child()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", help="the map's sample name")
    parser.add_argument("data_root", type=Path, nargs="?")
    parser.add_argument("derived_dir", type=Path, nargs="?")
    parser.add_argument("--box", type=int, nargs=4, metavar=("R0", "R1", "C0", "C1"))
    parser.add_argument("--polygon", nargs="+", metavar="R,C")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--save-errors",
        type=Path,
        metavar="FILE",
        help="write the per-bin errors of each region to FILE (the region's "
        "kind is inserted before the suffix)",
    )
    args = parser.parse_args(argv)

    data_root: Path | None = args.data_root
    derived_dir: Path | None = args.derived_dir
    if data_root is None or derived_dir is None:
        settings = Settings()
        data_root = data_root or Path(settings.data_root)
        if derived_dir is None:
            if settings.derived_data_dir is None:
                parser.error(f"{ENV_PREFIX}DERIVED_DATA_DIR is unset")
            derived_dir = Path(settings.derived_data_dir)

    spectraLogger.setLevel("WARNING")
    ops = OperationEDAXStateHandler(EDAXPathHandler(data_root, init_db=True))
    shape = ops.get_axis_sizes(args.sample)
    box, polygon = _default_regions(shape)
    if args.box:
        box = tuple(args.box)
    if args.polygon:
        polygon = [
            tuple(float(v) for v in vertex.split(",")) for vertex in args.polygon
        ]  # type: ignore[misc]
    store = DerivedDataStore(derived_dir, data_root, write_on_miss=False)
    fileset = ops.ph.get_sample_edax_file_names(args.sample)
    assert fileset is not None
    pyramid = store.load_pyramid(fileset)
    if pyramid is None:
        parser.error(f"no up-to-date pyramid for {args.sample} under {derived_dir}")
    print(f"{args.sample}: cube {shape}, pyramid block sizes {pyramid.block_sizes}")
    channel_axis = ops.get_sample_axes(args.sample)[2]
    energy_keV = channel_axis.offset + channel_axis.scale * np.arange(shape[2])

    regions: list[tuple[str, dict[str, object]]] = [
        (f"box {box}", {"box": list(box)}),
        (f"polygon ({len(polygon)} vertices)", {"polygon": polygon}),
    ]
    print(
        f"{'region':<34} {'method':<8} {'first s':>8} {'best s':>8} "
        f"{'peak RSS MB':>12} {'counts short':>13} {'shape err':>10}"
    )
    details: list[str] = []
    for label, region in regions:
        spectra: dict[str, list[int]] = {}
        pixels: dict[str, int] = {}
        for method in ("raw", "pyramid", "blocks"):
            result = _measure(
                data_root, derived_dir, args.sample, region, method, args.repeat
            )
            times = result["times"]
            assert isinstance(times, list)
            intensity = result["intensity"]
            assert isinstance(intensity, list)
            spectra[method] = intensity
            pixels[method] = int(result["pixels"])  # type: ignore[arg-type]
            error = ""
            if method == "blocks":
                shortfall, shape_error = _approximation_error(spectra["raw"], intensity)
                error = f" {100 * shortfall:>12.2f}% {100 * shape_error:>9.2f}%"
            print(
                f"{label:<34} {method:<8} "
                f"{times[0]:>8.3f} {min(times):>8.3f} {result['rss_peak_MB']:>12.0f}"
                f"{error}"
            )
        if spectra["raw"] != spectra["pyramid"]:
            print("  !! the raw and pyramid spectra disagree")
            return 1
        exact = np.asarray(spectra["raw"], dtype=np.float64)
        approx = np.asarray(spectra["blocks"], dtype=np.float64)
        details.append(label)
        details.extend(
            _per_bin_errors(exact, approx, pixels["raw"], pixels["blocks"], energy_keV)
        )
        if args.save_errors is not None:
            kind = "box" if "box" in region else "polygon"
            path = args.save_errors.with_name(
                f"{args.save_errors.stem}_{kind}{args.save_errors.suffix or '.csv'}"
            )
            _save_errors(
                path, label, energy_keV, exact, approx, pixels["raw"], pixels["blocks"]
            )
            details.append(f"    per-bin errors written to {path}")
    print()
    print("\n".join(details))
    return 0


if __name__ == "__main__":
    sys.exit(main())

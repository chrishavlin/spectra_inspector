"""Time a map's region spectra with and without its spectral block pyramid.

For a box and a polygon on one map, the spectrum is computed the way
``get_spectrum`` does it off the raw cube and then again from the pyramid in
the derived data directory (``scripts/build_spectral_pyramids.py`` builds
one), each in a fresh process so that the peak resident set size is that
request's alone. The two answers are checked to be identical. The cube is
whatever the page cache holds: run once to warm it, or drop the cache first
(``sudo purge`` on macOS, ``echo 3 > /proc/sys/vm/drop_caches`` on Linux) for
cold numbers.

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
    use_pyramid: bool,
    repeat: int,
) -> dict[str, object]:
    """One region, in a child process: wall time of each repeat, the peak RSS
    and a digest of the result."""
    task = {
        "data_root": str(data_root),
        "derived_dir": str(derived_dir),
        "sample": sample,
        "region": region,
        "use_pyramid": use_pyramid,
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
    kwargs: dict[str, object] = {"use_pyramid": task["use_pyramid"]}
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
    digest = None
    for _ in range(task["repeat"]):
        start = time.perf_counter()
        spectrum = ops.get_spectrum(task["sample"], **kwargs)  # type: ignore[arg-type]
        times.append(time.perf_counter() - start)
        digest = [int(spectrum.intensity.sum()), spectrum.intensity.tolist()[:8]]
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024  # bytes on macOS, KiB on Linux
    print(
        json.dumps(
            {
                "times": times,
                "rss_before_MB": before * scale / 2**20,
                "rss_peak_MB": after * scale / 2**20,
                "digest": digest,
            }
        )
    )
    return 0


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

    regions: list[tuple[str, dict[str, object]]] = [
        (f"box {box}", {"box": list(box)}),
        (f"polygon ({len(polygon)} vertices)", {"polygon": polygon}),
    ]
    print(
        f"{'region':<34} {'method':<8} {'first s':>8} {'best s':>8} {'peak RSS MB':>12}"
    )
    for label, region in regions:
        digests = []
        for use_pyramid in (False, True):
            result = _measure(
                data_root, derived_dir, args.sample, region, use_pyramid, args.repeat
            )
            times = result["times"]
            assert isinstance(times, list)
            digests.append(result["digest"])
            print(
                f"{label:<34} {'pyramid' if use_pyramid else 'raw':<8} "
                f"{times[0]:>8.3f} {min(times):>8.3f} {result['rss_peak_MB']:>12.0f}"
            )
        if digests[0] != digests[1]:
            print("  !! the two methods disagree")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "matplotlib>=3.10",
#   "numpy>=2.2",
#   "plotly>=6.6",
#   "rosettasciio>=0.14",
# ]
# ///
"""Render one EDAX map through every colormap the inspector offers, as a PDF.

Loads the EDAX fileset (``.spd`` + ``.spc`` + ``.ipr`` sharing a basename) in a
directory, sums the cube over the Mg energy window, and tiles the resulting
image once per colormap onto a multipage PDF (3 columns x 4 rows per page,
colormap name as the tile title).

The colormap list mirrors ``spectra_inspector.utilities.coerce
.get_sequential_colorscales``: plotly's sequential colorscales restricted to the
names matplotlib also knows. The loading mirrors the server's
``processor.file_loaders`` (rsciio for the metadata, a plain memmap of the
``.spd`` payload for the data).

Run it with uv, which resolves the dependencies above into an ephemeral
environment::

    uv run scripts/mg_colormap_gallery.py /path/to/dir [BASENAME] [-o OUT]

``BASENAME`` may be omitted when the directory holds a single ``.spd``.
``-o`` accepts either a ``.pdf`` path or a directory to write
``<basename>_Mg_colormaps.pdf`` into (default: the current directory).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import numpy.typing as npt
import plotly.express as px
from matplotlib import colormaps
from matplotlib.backends.backend_pdf import PdfPages
from rsciio import edax

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# same window the inspector's energy-range slider uses for Mg
MG_ENERGY_RANGE_KEV: tuple[float, float] = (1.16, 1.34)
N_COLS = 3
N_ROWS = 4

_mpl_cmaps_lower = {name.lower(): name for name in colormaps}


def get_sequential_colorscales() -> list[str]:
    """Plotly sequential colorscales that matplotlib also provides, sorted."""
    seq_attrs = {
        att.lower() for att in dir(px.colors.sequential) if not att.startswith("_")
    }
    names = [
        clr
        for clr in px.colors.named_colorscales()
        if clr.lower() in seq_attrs and clr.lower() in _mpl_cmaps_lower
    ]
    names.sort()
    return names


def resolve_fileset(directory: Path, basename: str | None) -> dict[str, Path]:
    """Locate the ``.spd``/``.spc``/``.ipr`` triple for ``basename`` in ``directory``."""
    if not directory.is_dir():
        msg = f"{directory} is not a directory"
        raise FileNotFoundError(msg)

    if basename is None:
        spds = sorted(directory.glob("*.spd"))
        if len(spds) != 1:
            found = ", ".join(p.stem for p in spds) or "none"
            msg = (
                f"expected exactly one .spd in {directory} when no basename is "
                f"given, found: {found}"
            )
            raise FileNotFoundError(msg)
        basename = spds[0].stem

    files = {ext: directory / f"{basename}.{ext}" for ext in ("spd", "spc", "ipr")}
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        msg = "missing EDAX files: " + ", ".join(missing)
        raise FileNotFoundError(msg)
    return files


def load_cube(
    files: dict[str, Path],
) -> tuple[npt.NDArray[Any], list[dict[str, Any]]]:
    """Memmap the ``.spd`` cube as (index0, index1, channel) plus its rsciio axes."""
    ds = edax.file_reader(
        files["spd"], spc_fname=files["spc"], ipr_fname=files["ipr"], lazy=True
    )
    header = ds[0]["original_metadata"]["spd_header"]
    nx, ny, nch = header["nPoints"], header["nLines"], header["nChannels"]
    dtype = {"1": "u1", "2": "u2", "4": "u4"}[str(header["countBytes"])]
    with files["spd"].open("rb") as f:
        raw = np.memmap(f, mode="r", offset=header["dataOffset"], dtype=dtype)
    cube = raw.squeeze().reshape((nch, nx, ny), order="F").T
    return cube, ds[0]["axes"]


def energy_to_channel_range(
    axes: list[dict[str, Any]], energy_range_kev: tuple[float, float]
) -> tuple[int, int]:
    """Map an energy window onto the (start, stop) channel slice the inspector uses."""
    energy_axis = next(ax for ax in axes if not ax["navigate"])
    scale = energy_axis["scale"]
    offset = energy_axis["offset"]
    size = energy_axis["size"]
    closest = [int(np.round((e - offset) / scale)) for e in energy_range_kev]
    start, stop = (min(max(c, 0), size) for c in closest)
    if stop <= start:
        msg = f"energy range {energy_range_kev} keV covers no channels"
        raise ValueError(msg)
    return start, stop


def summed_image(
    cube: npt.NDArray[Any], channel_range: tuple[int, int], chunksize: int = 128
) -> npt.NDArray[np.int64]:
    """Sum the cube over ``channel_range``, chunked along axis 0 like the server."""
    out = np.zeros(cube.shape[:2], dtype=np.int64)
    ch = slice(*channel_range)
    for start in range(0, cube.shape[0], chunksize):
        rows = slice(start, min(start + chunksize, cube.shape[0]))
        out[rows] = np.sum(cube[rows, :, ch], axis=-1, dtype=np.int64)
    return out


def write_gallery(
    image: npt.NDArray[Any],
    cmaps: list[str],
    pdf_path: Path,
    page_title: str,
) -> int:
    """Tile ``image`` under each colormap onto ``pdf_path``; returns the page count."""
    per_page = N_COLS * N_ROWS
    aspect = image.shape[0] / image.shape[1]
    tile_w = 3.0
    figsize = (N_COLS * tile_w, N_ROWS * tile_w * aspect + 0.6)
    vmin, vmax = float(image.min()), float(image.max())

    n_pages = 0
    with PdfPages(pdf_path) as pdf:
        for page_start in range(0, len(cmaps), per_page):
            page_cmaps = cmaps[page_start : page_start + per_page]
            fig, axes = plt.subplots(N_ROWS, N_COLS, figsize=figsize)
            for ax, name in zip(axes.flat, page_cmaps, strict=False):
                ax.imshow(
                    image, cmap=_mpl_cmaps_lower[name.lower()], vmin=vmin, vmax=vmax
                )
                ax.set_title(name, fontsize=10)
            for ax in axes.flat:
                ax.set_axis_off()
            fig.suptitle(page_title, fontsize=11)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
            n_pages += 1
    return n_pages


def resolve_output(output: Path | None, basename: str) -> Path:
    default_name = f"{basename}_Mg_colormaps.pdf"
    if output is None:
        return Path.cwd() / default_name
    if output.suffix.lower() == ".pdf":
        output.parent.mkdir(parents=True, exist_ok=True)
        return output
    output.mkdir(parents=True, exist_ok=True)
    return output / default_name


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "directory", type=Path, help="directory holding the EDAX fileset"
    )
    parser.add_argument(
        "basename",
        nargs="?",
        help="fileset basename (the .spd stem); optional if the directory has one .spd",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="a .pdf path, or a directory to write <basename>_Mg_colormaps.pdf into "
        "(default: current directory)",
    )
    parser.add_argument(
        "--energy-range",
        type=float,
        nargs=2,
        metavar=("E0", "E1"),
        default=MG_ENERGY_RANGE_KEV,
        help=f"energy window in keV to sum over (default: Mg, {MG_ENERGY_RANGE_KEV})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    files = resolve_fileset(args.directory, args.basename)
    basename = files["spd"].stem

    cube, axes = load_cube(files)
    energy_range = (float(args.energy_range[0]), float(args.energy_range[1]))
    channel_range = energy_to_channel_range(axes, energy_range)
    image = summed_image(cube, channel_range)

    cmaps = get_sequential_colorscales()
    pdf_path = resolve_output(args.output, basename)
    title = (
        f"{basename}: {energy_range[0]:g}-{energy_range[1]:g} keV "
        f"(channels {channel_range[0]}-{channel_range[1]})"
    )
    n_pages = write_gallery(image, cmaps, pdf_path, title)
    sys.stdout.write(
        f"wrote {len(cmaps)} colormaps over {n_pages} pages to {pdf_path}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

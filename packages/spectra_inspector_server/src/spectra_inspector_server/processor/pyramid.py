"""A spectral block pyramid: the cube summed over square spatial blocks, one
level per block size, stored as an OME-Zarr multiscales group.

A box or polygon selection sums the raw cube over its pixels, and that costs
the pixel area times a full spectrum of reads (the channel axis is the
contiguous one in the ``.spd`` layout). The pyramid trades disk for those
reads. Level ``k`` holds, for every ``b_k x b_k`` block of the map, the sum of
its pixels' spectra, with the channel axis left whole; the block sizes grow by
an integer factor from one level to the next, so a coarse block is exactly
the sum of the fine blocks it covers. Level 0 is already a downsampling, never
the raw cube, which stays the only copy of the pixels.

A selection's spectrum is then exact as the sum of the entries of every block
that lies entirely inside it, taken from the coarsest level that still fits,
plus the raw spectra of the pixels the boundary cuts through. Raw reads scale
with the perimeter times the finest block size rather than the area, and the
reads of each level come one zarr chunk at a time, so a request never holds
more than a chunk of a level and a bounded batch of raw pixels at once. The
boundary of a block in the pyramid is the boundary of its pixels' footprint,
so a map whose shape is not a multiple of a block size simply has smaller
blocks along its bottom and right edges; a pixel past the edge belongs to no
block and is never counted.

The store is a zarr v3 group laid out as OME-NGFF 0.5 ``multiscales``: arrays
``"0"``, ``"1"``, ... from finest to coarsest, each ``(blocks0, blocks1,
channels)``. The spec requires a ``scale`` transformation per level, here
``(b_k, b_k, 1)``, and the optional ``translation`` records that a block's
centre sits at pixel ``i * b_k + (b_k - 1) / 2``; the server reads neither,
it works from the block sizes in the group's own attribute. NGFF treats a
coarser level as a rendering of the finer one and has no way to say "sum",
so the ``type`` is recorded as ``sum``. Only the ``zarr`` package is used:
``ome-zarr`` would add dask and scikit-image to the server for a few lines
of metadata. The group's
``spectra_inspector`` attribute carries the same kind of key the derived data
store uses (``processor/derived_data.py``), so a pyramid built for an older
``.spd`` is a miss, not a wrong answer.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import zarr
import zarr.codecs

from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.processor._reductions import (
    accumulator_dtype,
    chunk_bounds,
)

# block edge of each level in pixels, finest first: 4x4, 16x16, 64x64
DEFAULT_BLOCK_SIZES: tuple[int, ...] = (4, 16, 64)
PYRAMID_DIRNAME = "pyramid.zarr"
NGFF_VERSION = "0.5"

MIN_BLOCK_SIZE = 2

_ATTR = "spectra_inspector"
_KIND = "spectral_block_pyramid"
_FORMAT_VERSION = 1
_AXES = (
    {"name": "index0", "type": "space"},
    {"name": "index1", "type": "space"},
    {"name": "channel", "type": "channel"},
)
# the raw pixels a request gathers at once; at 4096 uint16 channels, 32 MB
_RAW_PIXEL_BATCH = 4096
# the raw rows the build reads at once, as a multiple of the coarsest block
_BUILD_SLAB_BYTES = 256 * 2**20


@dataclass(frozen=True)
class PyramidSpec:
    """How a pyramid is laid out.

    Parameters
    ----------
    block_sizes : tuple[int, ...]
        the block edge of each level in pixels, finest level first. Each must
        be at least 2 (level 0 is a downsampling, not the raw cube) and a
        multiple of the one before it, so the number of entries is the number
        of levels and the ratio of neighbours the refinement factor between
        them.
    chunk_blocks : int
        the edge of a zarr chunk, in blocks; every chunk spans all channels.
    """

    block_sizes: tuple[int, ...] = DEFAULT_BLOCK_SIZES
    chunk_blocks: int = 16

    def __post_init__(self) -> None:
        sizes = tuple(int(b) for b in self.block_sizes)
        object.__setattr__(self, "block_sizes", sizes)
        if not sizes:
            msg = "a pyramid needs at least one level"
            raise ValueError(msg)
        if sizes[0] < MIN_BLOCK_SIZE:
            msg = f"the finest block size must be at least {MIN_BLOCK_SIZE}, got {sizes[0]}"
            raise ValueError(msg)
        for fine, coarse in zip(sizes, sizes[1:], strict=False):
            if coarse <= fine or coarse % fine:
                msg = (
                    f"block sizes must grow by an integer factor from one level "
                    f"to the next, got {sizes}"
                )
                raise ValueError(msg)
        if self.chunk_blocks < 1:
            msg = f"chunk_blocks must be at least 1, got {self.chunk_blocks}"
            raise ValueError(msg)

    @classmethod
    def from_factors(cls, base: int, factors: tuple[int, ...]) -> "PyramidSpec":
        """A spec from the finest block size and the refinement factor of
        every further level: ``from_factors(4, (4, 4))`` is ``(4, 16, 64)``."""
        sizes = [int(base)]
        for factor in factors:
            sizes.append(sizes[-1] * int(factor))
        return cls(block_sizes=tuple(sizes))

    @property
    def n_levels(self) -> int:
        return len(self.block_sizes)

    @property
    def refinement_factors(self) -> tuple[int, ...]:
        """The factor by which each level coarsens the one before it."""
        return tuple(
            coarse // fine
            for fine, coarse in zip(
                self.block_sizes, self.block_sizes[1:], strict=False
            )
        )


def level_shape(
    source_shape: tuple[int, int, int], block_size: int
) -> tuple[int, int, int]:
    """The ``(blocks0, blocks1, channels)`` shape of a level: a partial block
    along the bottom or right edge still counts as one."""
    rows, cols, channels = source_shape
    return (math.ceil(rows / block_size), math.ceil(cols / block_size), channels)


def block_sum(
    array: npt.NDArray[Any], block_size: int, out_dtype: np.dtype
) -> npt.NDArray[Any]:
    """``array`` summed over ``block_size x block_size`` blocks of its first two
    axes, the last axis kept. The bottom and right edge blocks are smaller
    when the shape does not divide; no padding is added, so a C-contiguous
    input whose width divides is reduced without a copy."""
    n0, n1, channels = array.shape
    b = block_size
    m0, m1 = math.ceil(n0 / b), math.ceil(n1 / b)
    f0, f1 = (n0 // b) * b, (n1 // b) * b
    out = np.zeros((m0, m1, channels), dtype=out_dtype)
    if f0 and f1:
        out[: f0 // b, : f1 // b] = (
            array[:f0, :f1]
            .reshape(f0 // b, b, f1 // b, b, channels)
            .sum(axis=(1, 3), dtype=out_dtype)
        )
    if f0 and f1 < n1:
        out[: f0 // b, m1 - 1] = (
            array[:f0, f1:]
            .reshape(f0 // b, b, n1 - f1, channels)
            .sum(axis=(1, 2), dtype=out_dtype)
        )
    if f0 < n0 and f1:
        out[m0 - 1, : f1 // b] = (
            array[f0:, :f1]
            .reshape(n0 - f0, f1 // b, b, channels)
            .sum(axis=(0, 2), dtype=out_dtype)
        )
    if f0 < n0 and f1 < n1:
        out[m0 - 1, m1 - 1] = array[f0:, f1:].sum(axis=(0, 1), dtype=out_dtype)
    return out


def pyramid_dtype(source_dtype: np.dtype, spec: PyramidSpec) -> np.dtype:
    """One dtype for every level: the narrowest that holds a coarsest block."""
    return accumulator_dtype(source_dtype, spec.block_sizes[-1] ** 2)


def write_pyramid(
    path: Path,
    data: npt.NDArray[Any],
    spec: PyramidSpec,
    key: dict[str, Any],
    name: str = "",
) -> None:
    """Build the pyramid of ``data`` (a ``(index0, index1, channel)`` cube,
    usually the memmap) at ``path``, replacing whatever is there.

    The cube is read once, a slab of rows at a time; level 0 of a slab is
    summed straight off the cube and every coarser level off level 0, so
    nothing larger than a slab's worth of level 0 is ever in memory. ``key``
    is stored verbatim for the reader to check against the source file.
    """
    if data.ndim != 3:
        msg = f"expected a (index0, index1, channel) cube, got shape {data.shape}"
        raise ValueError(msg)
    source_shape = (int(data.shape[0]), int(data.shape[1]), int(data.shape[2]))
    rows, cols, channels = source_shape
    dtype = pyramid_dtype(data.dtype, spec)
    coarsest = spec.block_sizes[-1]

    group = zarr.open_group(path, mode="w", zarr_format=3)
    levels: list[zarr.Array[Any]] = []
    for level, b in enumerate(spec.block_sizes):
        shape = level_shape(source_shape, b)
        chunks = (
            min(spec.chunk_blocks, shape[0]),
            min(spec.chunk_blocks, shape[1]),
            channels,
        )
        levels.append(
            group.create_array(
                str(level),
                shape=shape,
                chunks=chunks,
                dtype=dtype,
                compressors=zarr.codecs.BloscCodec(
                    cname="zstd", clevel=3, shuffle="shuffle"
                ),
                dimension_names=tuple(ax["name"] for ax in _AXES),
            )
        )

    slab_rows = max(
        coarsest,
        (_BUILD_SLAB_BYTES // max(cols * channels * data.dtype.itemsize, 1))
        // coarsest
        * coarsest,
    )
    finest = spec.block_sizes[0]
    for r0, r1 in chunk_bounds(0, rows, slab_rows):
        level0 = block_sum(data[r0:r1], finest, dtype)
        levels[0][r0 // finest : r0 // finest + level0.shape[0]] = level0
        for level, b in enumerate(spec.block_sizes[1:], start=1):
            coarse = block_sum(level0, b // finest, dtype)
            levels[level][r0 // b : r0 // b + coarse.shape[0]] = coarse

    group.update_attributes(
        {
            "ome": _multiscales_metadata(spec, name),
            _ATTR: {
                "kind": _KIND,
                "format_version": _FORMAT_VERSION,
                "key": key,
                "block_sizes": list(spec.block_sizes),
                "source_shape": list(source_shape),
                "source_dtype": data.dtype.str,
            },
        }
    )


def _multiscales_metadata(spec: PyramidSpec, name: str) -> dict[str, Any]:
    datasets = []
    for level, b in enumerate(spec.block_sizes):
        # block (i, j) covers pixels [i*b, (i+1)*b): its centre, in pixel
        # units, sits (b - 1) / 2 past the pixel i*b
        datasets.append(
            {
                "path": str(level),
                "coordinateTransformations": [
                    {"type": "scale", "scale": [float(b), float(b), 1.0]},
                    {
                        "type": "translation",
                        "translation": [(b - 1) / 2, (b - 1) / 2, 0.0],
                    },
                ],
            }
        )
    multiscale: dict[str, Any] = {
        "axes": [dict(ax) for ax in _AXES],
        "datasets": datasets,
        "type": "sum",
        "metadata": {
            "description": (
                "each level sums the spectra of the pixels in a block of the "
                "map (not an average): a block's counts, with the channel axis "
                "left whole"
            ),
            "block_sizes": list(spec.block_sizes),
        },
    }
    if name:
        multiscale["name"] = name
    return {"version": NGFF_VERSION, "multiscales": [multiscale]}


@dataclass(frozen=True)
class PyramidReadStats:
    """What answering a region request cost: how many block entries each
    level supplied, finest level first, and how many raw pixels were read of
    the pixels selected."""

    blocks_per_level: tuple[int, ...]
    raw_pixels: int
    selected_pixels: int


class SpectralPyramid:
    """A pyramid group opened for reading.

    Parameters
    ----------
    group : zarr.Group
        the group ``write_pyramid`` wrote
    """

    def __init__(self, group: zarr.Group) -> None:
        attrs = dict(group.attrs)
        info = attrs.get(_ATTR)
        if not isinstance(info, dict) or info.get("kind") != _KIND:
            msg = f"{group.store} is not a spectral block pyramid"
            raise ValueError(msg)
        self.key: dict[str, Any] = dict(info["key"])
        self.block_sizes: tuple[int, ...] = tuple(int(b) for b in info["block_sizes"])
        shape = info["source_shape"]
        self.source_shape: tuple[int, int, int] = (
            int(shape[0]),
            int(shape[1]),
            int(shape[2]),
        )
        self.spec = PyramidSpec(block_sizes=self.block_sizes)
        self.levels: list[zarr.Array[Any]] = []
        for level, b in enumerate(self.block_sizes):
            array = group[str(level)]
            if not isinstance(array, zarr.Array):
                msg = f"level {level} of {group.store} is not an array"
                raise TypeError(msg)
            expected = level_shape(self.source_shape, b)
            if tuple(array.shape) != expected:
                msg = f"level {level} has shape {array.shape}, expected {expected}"
                raise ValueError(msg)
            self.levels.append(array)

    @classmethod
    def open(cls, path: str | Path) -> "SpectralPyramid":
        return cls(zarr.open_group(path, mode="r"))

    def region_spectrum(
        self,
        data: npt.NDArray[Any],
        mask: npt.NDArray[np.bool_] | None,
        index0_range: tuple[int, int],
        index1_range: tuple[int, int],
        channel_range: tuple[int, int],
    ) -> tuple[npt.NDArray[np.int64], PyramidReadStats]:
        """The spectrum summed over a region of the map, exactly.

        Parameters
        ----------
        data : NDArray
            the raw cube the pyramid was built from, for the boundary pixels
        mask : NDArray[bool] | None
            which pixels of the box ``index0_range x index1_range`` are in
            the region, as ``polygon_mask`` gives it; None selects the whole
            box
        index0_range, index1_range : tuple[int, int]
            the half-open index ranges of the box, within the map
        channel_range : tuple[int, int]
            the half-open channel range to return

        Returns
        -------
        tuple[NDArray[int64], PyramidReadStats]
            the spectrum over ``channel_range`` and what it cost
        """
        if tuple(data.shape) != self.source_shape:
            msg = f"the cube has shape {data.shape}, the pyramid was built from {self.source_shape}"
            raise ValueError(msg)
        rows, cols, _ = self.source_shape
        r0, r1 = index0_range
        c0, c1 = index1_range
        ch0, ch1 = channel_range
        out = np.zeros(max(ch1 - ch0, 0), dtype=np.int64)
        if mask is None:
            mask = np.ones((max(r1 - r0, 0), max(c1 - c0, 0)), dtype=np.bool_)
        if mask.shape != (r1 - r0, c1 - c0):
            msg = f"mask shape {mask.shape} does not span the box {(r1 - r0, c1 - c0)}"
            raise ValueError(msg)
        n_blocks = [0] * len(self.block_sizes)
        selected = int(mask.sum())
        if selected == 0 or out.size == 0:
            return out, PyramidReadStats(tuple(n_blocks), 0, selected)

        # the box widened to whole blocks of the coarsest level, which every
        # finer level then also tiles. Pixels past the map's edge count as
        # selected: an edge block holds only the pixels that exist, so it is
        # inside the region when those are.
        coarsest = self.block_sizes[-1]
        ra0, ca0 = (r0 // coarsest) * coarsest, (c0 // coarsest) * coarsest
        ra1 = math.ceil(r1 / coarsest) * coarsest
        ca1 = math.ceil(c1 / coarsest) * coarsest
        remaining = np.zeros((ra1 - ra0, ca1 - ca0), dtype=np.bool_)
        remaining[r0 - ra0 : r1 - ra0, c0 - ca0 : c1 - ca0] = mask
        remaining[rows - ra0 :, :] = True
        remaining[:, cols - ca0 :] = True

        for level in reversed(range(len(self.block_sizes))):
            b = self.block_sizes[level]
            array = self.levels[level]
            h, w = remaining.shape
            full = np.asarray(
                remaining.reshape(h // b, b, w // b, b).all(axis=(1, 3)), dtype=np.bool_
            )
            i0, j0 = ra0 // b, ca0 // b
            # blocks lying wholly past the map's edge do not exist
            full[array.shape[0] - i0 :, :] = False
            full[:, array.shape[1] - j0 :] = False
            n_blocks[level] = int(full.sum())
            if n_blocks[level] == 0:
                continue
            out += _sum_blocks(array, full, i0, j0, ch0, ch1)
            remaining &= ~np.repeat(np.repeat(full, b, axis=0), b, axis=1)

        leftover = remaining[r0 - ra0 : r1 - ra0, c0 - ca0 : c1 - ca0]
        raw_pixels = int(leftover.sum())
        if raw_pixels:
            out += _sum_raw_pixels(data, leftover, r0, c0, ch0, ch1)
        stats = PyramidReadStats(tuple(n_blocks), raw_pixels, selected)
        spectraLogger.debug("pyramid: %s", stats)
        return out, stats


def _sum_blocks(
    array: zarr.Array[Any],
    full: npt.NDArray[np.bool_],
    i0: int,
    j0: int,
    ch0: int,
    ch1: int,
) -> npt.NDArray[np.int64]:
    """The entries of ``array`` flagged in ``full`` (whose origin is block
    ``(i0, j0)``) summed, one zarr chunk at a time."""
    out = np.zeros(ch1 - ch0, dtype=np.int64)
    bi, bj = np.nonzero(full)
    gi, gj = bi + i0, bj + j0
    rows_per_chunk, cols_per_chunk = int(array.chunks[0]), int(array.chunks[1])
    n_chunk_cols = math.ceil(array.shape[1] / cols_per_chunk)
    chunk_ids = (gi // rows_per_chunk) * n_chunk_cols + gj // cols_per_chunk
    for chunk_id in np.unique(chunk_ids):
        in_chunk = chunk_ids == chunk_id
        ci, cj = divmod(int(chunk_id), n_chunk_cols)
        rs, re = ci * rows_per_chunk, min((ci + 1) * rows_per_chunk, array.shape[0])
        cs, ce = cj * cols_per_chunk, min((cj + 1) * cols_per_chunk, array.shape[1])
        slab = np.asarray(array[rs:re, cs:ce, ch0:ch1])
        local = np.zeros((re - rs, ce - cs), dtype=np.bool_)
        local[gi[in_chunk] - rs, gj[in_chunk] - cs] = True
        out += slab[local].sum(axis=0, dtype=np.int64)
    return out


def _sum_raw_pixels(
    data: npt.NDArray[Any],
    leftover: npt.NDArray[np.bool_],
    r0: int,
    c0: int,
    ch0: int,
    ch1: int,
) -> npt.NDArray[np.int64]:
    """The spectra of the pixels flagged in ``leftover`` (whose origin is
    pixel ``(r0, c0)``) gathered from the cube a bounded batch at a time."""
    out = np.zeros(ch1 - ch0, dtype=np.int64)
    ri, ci = np.nonzero(leftover)
    ri = ri + r0
    ci = ci + c0
    for start, stop in chunk_bounds(0, len(ri), _RAW_PIXEL_BATCH):
        batch = data[ri[start:stop], ci[start:stop], ch0:ch1]
        out += batch.sum(axis=0, dtype=accumulator_dtype(data.dtype, stop - start))
    return out


__all__ = [
    "DEFAULT_BLOCK_SIZES",
    "PYRAMID_DIRNAME",
    "PyramidReadStats",
    "PyramidSpec",
    "SpectralPyramid",
    "block_sum",
    "level_shape",
    "pyramid_dtype",
    "write_pyramid",
]

"""Rasterise a polygon drawn over the map into a pixel mask.

The frontend sends the polygon as ordered vertices in index units, the same
grid the map's pixels sit on: vertex ``(i, j)`` is the centre of the pixel in
row ``i``, column ``j``. A pixel belongs to the region when its centre falls
inside the polygon (even-odd rule), and the mask only spans the polygon's
bounding box so a small region on a large map costs little.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

Vertex = tuple[float, float]
IndexRange = tuple[int, int]

MIN_VERTICES = 3


def polygon_bounds(
    vertices: Sequence[Vertex] | npt.NDArray[np.float64], shape: tuple[int, int]
) -> tuple[IndexRange, IndexRange]:
    """The half-open index ranges of the pixels whose centres a polygon can
    reach on each axis, clipped to an image of ``shape`` (rows, columns).

    A polygon lying entirely off the image gives an empty range.
    """
    verts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    ranges: list[IndexRange] = []
    for axis, size in enumerate(shape):
        lo = int(np.ceil(verts[:, axis].min()))
        hi = int(np.floor(verts[:, axis].max())) + 1
        lo = min(max(lo, 0), size)
        hi = min(max(hi, lo), size)
        ranges.append((lo, hi))
    return ranges[0], ranges[1]


def polygon_mask(
    vertices: Sequence[Vertex], shape: tuple[int, int]
) -> tuple[npt.NDArray[np.bool_], IndexRange, IndexRange]:
    """The pixels inside a polygon, over its bounding box.

    Parameters
    ----------
    vertices : Sequence[tuple[float, float]]
        the polygon's corners in order, as ``(index0, index1)`` pairs (row,
        column) in pixel-index units. The last vertex joins back to the first.
    shape : tuple[int, int]
        the image's ``(rows, columns)``.

    Returns
    -------
    tuple[NDArray[bool], tuple[int, int], tuple[int, int]]
        ``(mask, index0_range, index1_range)``: a boolean array covering the
        polygon's bounding box, clipped to the image, and the half-open index
        ranges that box spans on each axis.
    """
    verts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    if len(verts) < MIN_VERTICES:
        msg = f"a polygon needs at least {MIN_VERTICES} vertices, got {len(verts)}"
        raise ValueError(msg)
    if not np.all(np.isfinite(verts)):
        msg = "polygon vertices must be finite"
        raise ValueError(msg)

    (r0, r1), (c0, c1) = polygon_bounds(verts, shape)
    rows = np.arange(r0, r1, dtype=np.float64)[:, np.newaxis]
    cols = np.arange(c0, c1, dtype=np.float64)[np.newaxis, :]
    inside = np.zeros((r1 - r0, c1 - c0), dtype=np.bool_)

    # even-odd rule: a pixel centre is inside when a ray from it along the
    # column axis crosses an odd number of edges. Each edge is half-open in
    # the row direction so a ray through a vertex counts its two edges once.
    for start, stop in zip(verts, np.roll(verts, -1, axis=0), strict=True):
        ra, ca = start
        rb, cb = stop
        if ra == rb:
            continue
        spans = (rows >= min(ra, rb)) & (rows < max(ra, rb))
        col_at_row = ca + (rows - ra) * (cb - ca) / (rb - ra)
        inside ^= spans & (cols < col_at_row)

    return inside, (r0, r1), (c0, c1)

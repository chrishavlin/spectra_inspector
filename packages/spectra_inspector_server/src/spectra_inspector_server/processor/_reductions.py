"""Helpers for reducing the on-disk spectrum cube a chunk at a time.

The cube is a read-only memmap, so a reduction is a stream of page faults plus
a numpy accumulation loop. What dominates the loop is the accumulator dtype:
numpy's 32 bit reduce loop is about twice as fast as the 64 bit one, so use the
narrowest accumulator that provably cannot overflow (:func:`accumulator_dtype`).
"""

import numpy as np


def accumulator_dtype(data_dtype: np.dtype, n_terms: int) -> np.dtype:
    """The narrowest fast accumulator that cannot overflow.

    Parameters
    ----------
    data_dtype : np.dtype
        dtype of the values being summed.
    n_terms : int
        how many values are summed into a single accumulator element.
    """
    if not np.issubdtype(data_dtype, np.integer):
        return np.dtype(np.float64)

    info = np.iinfo(data_dtype)
    largest = n_terms * max(abs(info.min), info.max)
    if info.min == 0:
        if largest <= np.iinfo(np.uint32).max:
            return np.dtype(np.uint32)
    elif largest <= np.iinfo(np.int32).max:
        return np.dtype(np.int32)
    return np.dtype(np.int64)


def fast_accumulator_limit(data_dtype: np.dtype) -> int:
    """Largest ``n_terms`` for which :func:`accumulator_dtype` stays 32 bit.

    Lets a caller that is free to choose its chunking pick chunks small enough
    to keep the fast accumulator. Zero when no chunking can achieve that.
    """
    if not np.issubdtype(data_dtype, np.integer):
        return 0
    info = np.iinfo(data_dtype)
    widest = np.iinfo(np.uint32) if info.min == 0 else np.iinfo(np.int32)
    return int(widest.max // max(abs(info.min), info.max))


def chunk_bounds(start: int, stop: int, chunksize: int) -> list[tuple[int, int]]:
    """Split ``[start, stop)`` into contiguous chunks of at most ``chunksize``."""
    return [(c, min(c + chunksize, stop)) for c in range(start, stop, chunksize)]

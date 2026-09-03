from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from rsciio import edax

from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.model import EDAX_file_set, EDAX_raw_ds


def load_edax_spd_metadata(edax_files: EDAX_file_set) -> dict[str, Any]:
    # load the metadata, always use lazy load
    ds = edax.file_reader(edax_files.spd, ipr_fname=edax_files.ipr, lazy=True)
    if len(ds) > 1:
        msg = f"The following EDAX file includes more than one ds object, only the first will be loaded: {edax_files.spd}"
        spectraLogger.info(msg)

    return {
        "axes": ds[0]["axes"],
        "metadata": ds[0]["metadata"],
        "original_metadata": ds[0]["original_metadata"],
    }


def load_spd_into_memmap(
    header: dict[str, Any], spd_path: str
) -> npt.NDArray[np.int64]:
    # rsciio replaced plain np.memmap with a dask-wrapped memmap. for now,
    # using a plain memmap to avoid dask dependency within fastapi.

    nx = header["nPoints"]
    ny = header["nLines"]
    nCh = header["nChannels"]
    offset = header["dataOffset"]
    nbytes = str(header["countBytes"])
    data_type = {"1": "u1", "2": "u2", "4": "u4"}[nbytes]

    with Path(spd_path).open("rb") as f:
        # Read data from file into a numpy memmap object
        data: npt.NDArray[np.int64] = np.memmap(
            f, mode="r", offset=offset, dtype=data_type
        )
    data = data.squeeze().reshape((nCh, nx, ny), order="F").T
    return data


_CacheKey = tuple[str, bool]
_CacheEntry = tuple[tuple[int, int], EDAX_raw_ds]
# Mapping a fileset is cheap but *using* it is not: faulting a whole cube's
# worth of pages into a fresh mapping costs tens of ms even when the file is
# already in the page cache, so hold the mapping open between requests.
_MAX_CACHED_FILESETS = 4
_ds_cache: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()


def _file_stamp(spd: Path) -> tuple[int, int]:
    stat = spd.stat()
    return (stat.st_mtime_ns, stat.st_size)


def clear_edax_cache() -> None:
    _ds_cache.clear()


def load_edax_spd(
    edax_files: EDAX_file_set, metadata_only: bool = False
) -> EDAX_raw_ds:
    key = (str(edax_files.spd), metadata_only)
    stamp = _file_stamp(edax_files.spd)
    cached = _ds_cache.get(key)
    if cached is not None:
        if cached[0] == stamp:
            _ds_cache.move_to_end(key)
            return cached[1]
        del _ds_cache[key]

    md = load_edax_spd_metadata(edax_files)
    if not metadata_only:
        data = load_spd_into_memmap(
            md["original_metadata"]["spd_header"], str(edax_files.spd)
        )
        md.update({"data": data})

    ds = EDAX_raw_ds(md)
    _ds_cache[key] = (stamp, ds)
    while len(_ds_cache) > _MAX_CACHED_FILESETS:
        _ds_cache.popitem(last=False)
    return ds


def find_data_start(msa_path: str) -> int:
    idx = 0
    with open(msa_path) as fh:
        while True:
            idx += 1
            msa_data = fh.readline()
            if "Spectral Data Starts Here" in msa_data:
                return idx
            if idx > 100:
                msg = "Could not identify starting row for msa data"
                raise RuntimeError(msg)


def load_msa(msa_path: str) -> pd.DataFrame:
    # Note: rosetasciio supports "Y" and "XY" formats, this loader assumes "XY".
    # TODO: handle "Y", also save the metadata.
    idx = find_data_start(msa_path)
    # engine='python' to avoid warning using skipfooter
    return pd.read_csv(
        msa_path,
        skiprows=idx,
        header=None,
        names=["x", "intensity"],
        skipfooter=1,
        engine="python",
    )

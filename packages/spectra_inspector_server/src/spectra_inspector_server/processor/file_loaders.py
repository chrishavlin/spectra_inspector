import numpy as np
import pandas as pd
from rsciio import edax

from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.model import EDAX_file_set, EDAX_raw_ds


def load_edax_spd_metadata(edax_files: EDAX_file_set) -> dict[str, str]:
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


def load_spd_into_memmap(header: dict, spd_path: str) -> np.memmap:
    # rsciio replaced plain np.memmap with a dask-wrapped memmap. for now,
    # using a plain memmap to avoid dask dependency within fastapi.

    nx = header["nPoints"]
    ny = header["nLines"]
    nCh = header["nChannels"]
    offset = header["dataOffset"]
    nbytes = str(header["countBytes"])
    data_type = {"1": "u1", "2": "u2", "4": "u4"}[nbytes]

    with open(spd_path) as f:
        # Read data from file into a numpy memmap object
        data = np.memmap(f, mode="r", offset=offset, dtype=data_type)
    return data.squeeze().reshape((nx, ny, nCh), order="F")


def load_edax_spd(
    edax_files: EDAX_file_set, metadata_only: bool = False
) -> EDAX_raw_ds:
    md = load_edax_spd_metadata(edax_files)
    if metadata_only:
        return EDAX_raw_ds(md)
    data = load_spd_into_memmap(md["original_metadata"]["spd_header"], edax_files.spd)
    md.update({"data": data})
    return EDAX_raw_ds(md)


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

import pandas as pd
from rsciio import edax

from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.model import EDAX_file_set, EDAX_raw_ds


def load_edax_spd(edax_files: EDAX_file_set) -> EDAX_raw_ds:
    ds = edax.file_reader(edax_files.spd, ipr_fname=edax_files.ipr)  # type: ignore[no-untyped-call]
    if len(ds) > 1:
        msg = f"The following EDAX file includes more than one ds object, only the first will be loaded: {edax_files.spd}"
        spectraLogger.info(msg)

    return EDAX_raw_ds(ds[0])


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

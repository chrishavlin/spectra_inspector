import pandas as pd

from spectra_inspector_server.model import EDAX_file_set, EDAX_raw_ds
from spectra_inspector_server.processor import edax_reader


def load_edax_spd(
    edax_files: EDAX_file_set, metadata_only: bool = False
) -> EDAX_raw_ds:
    return edax_reader.load_edax_spd(edax_files, metadata_only=metadata_only)


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

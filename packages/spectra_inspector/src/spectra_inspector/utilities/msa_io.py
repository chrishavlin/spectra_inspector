from pathlib import Path
from typing import Literal

import pandas as pd
from rsciio.msa import file_writer


def read_msa_XY(msa_file: str | Path) -> pd.DataFrame:
    """
    Read the spectral data from an EMSA/MSA file written in XY format.

    Parameters
    ----------
    msa_file
        Path to the .msa file.

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns:
            - energy_keV
            - intensity
    """
    msa_file = Path(msa_file)

    # Find the line where the spectral data begins.
    with msa_file.open() as f:
        for i, line in enumerate(f):
            if line.startswith("#SPECTRUM"):
                spectrum_line = i
                break
        else:
            msg = f"Could not find '#SPECTRUM' section in {msa_file}"
            raise ValueError(msg)

    return pd.read_csv(
        msa_file,
        skiprows=spectrum_line + 1,
        skipfooter=1,  # Skip the '#ENDOFDATA' line.
        engine="python",  # Required when using skipfooter.
        names=["energy_keV", "intensity"],
        sep=r"\s*,\s*",
    )


def write_MSA(
    f: str | Path,
    intensity,
    energy,
    attrs: dict,
    file_format: Literal["Y", "XY"] = "XY",
) -> Path:
    """
    Write an EMSA/MSA spectrum.

    Parameters
    ----------
    f
        Output filename.
    intensity
        1D array of intensities.
    energy
        1D array of energy values (keV).
    attrs
        Dictionary containing 'metadata' and 'original_metadata'.
    file_format
        MSA data format ("Y" or "XY").

    Returns
    -------
    Path
        Path to the written file.
    """
    f = Path(f)

    signal = {
        "data": intensity,
        "axes": [
            {
                "size": len(intensity),
                "index_in_array": 0,
                "name": "Energy",
                "scale": energy[1] - energy[0],
                "offset": energy[0],
                "units": "keV",
                "navigate": False,
            }
        ],
        "metadata": attrs["metadata"],
        "original_metadata": attrs["original_metadata"],
    }

    file_writer(f, signal, format=file_format)

    return f

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "latloncalc>=1.5.6",
#     "numpy>=2.4.4",
#     "pandas>=3.0.2",
# ]
# ///

# one-off script for cleaning up the lat/lon spreadsheet. run with
#
# uv run clean_latlon_torres_csv.py /path/to/TorresSampleLocation-prepped.csv
#
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from latloncalc.latlon import string2latlon

spectraLogger = logging.getLogger("spectra_inspector_utility")
spectraLogger.setLevel(logging.INFO)


def clean_row(row):

    if row["gps"] == '"':
        row["gps"] = np.nan
    elif str(row["gps"]).startswith("*") or str(row["gps"]).endswith("*"):
        row["gps_quality_note"] = "approximate"
        row["gps"] = str(row["gps"]).replace("*", "")
    elif str(row["gps"]).strip() in ("?", "float"):
        val = row["gps"]
        note = f"gps init value {val}, assuming prior;"
        newval = row["processing_note"] + note
        row["gps"] = np.nan
        row["processing_note"] = newval

    if row["elevation"] in ("?", ":"):
        val = row["elevation"]
        row["elevation"] = np.nan
        note = f"elevation init value {val}, assuming prior;"
        row["processing_note"] = row["processing_note"] + note
    elif str(row["elevation"]).startswith("*"):
        row["elvation_quality_note"] = "approximate"
        row["elevation"] = str(row["elevation"]).replace("*", "")
    elif str(row["elevation"]) == '"':
        row["elevation"] = np.nan

    return row


def split_gps_row(row):

    gpsstr = row["gps"]

    latlon = gpsstr.split(" ")
    latlon_strs = []
    for ll in [latlon[0], latlon[-1]]:
        ll_valid = ll.replace("'", " ").replace("°", " ").replace('"', " ")
        latlon_strs.append(ll_valid)

    palmyra = string2latlon(latlon_strs[0], latlon_strs[1], "d% %m% %S% %H")

    row["lat_str"] = latlon_strs[0]
    row["lon_str"] = latlon_strs[1]
    row["lon"] = palmyra.lon.decimal_degree
    row["lat"] = palmyra.lat.decimal_degree
    return row


def clean_torres_csv(fname: Path):
    df = pd.read_csv(fname)

    # first remove empty rows
    df = df.dropna(how="all")

    # lets clean up column names
    cols = {col: str(col).replace(" ", "_").lower() for col in df.columns}
    df = df.rename(columns=cols)

    # fill in group name
    df["group_name"] = df["group_name"].ffill()

    # add new columns

    df["gps_quality_note"] = ""
    df["elvation_quality_note"] = ""
    df["processing_note"] = ""
    df["lat_str"] = ""
    df["lon_str"] = ""
    df["lat"] = 0.0
    df["lon"] = 0.0

    # now the tough stuff
    df = df.apply(clean_row, axis=1)
    df["gps"] = df["gps"].ffill()
    df["elevation"] = df["elevation"].ffill()

    df = df.apply(split_gps_row, axis=1)
    df["location_notes"] = df["location_notes"].fillna("")
    return df.reset_index(drop=True)


def main() -> None:
    f = Path(sys.argv[1])
    df = clean_torres_csv(f)
    fout = f.parent / "sample_metadata.csv"
    msg = f"writing {fout}"
    spectraLogger.info(msg)
    df.to_csv(fout, index=False)


if __name__ == "__main__":
    main()

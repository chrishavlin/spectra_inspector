import json
from pathlib import Path

import pandas as pd

from spectra_inspector_server.model import sampleMetadata, sampleMetadataCSVrecord

# expected CSV format
#
# group_name,sample_name,sample_type,description,gps,elevation,location_notes,gps_quality_note,elvation_quality_note,processing_note,lat_str,lon_str,lat,lon
# C-12, -50.953878, -72.983542


class SampleMetadataMapper:
    sample_metadata_fullpath: Path | None
    exists: bool
    _df: pd.DataFrame | None = None
    expected_cols = ("sample_id", "lat", "lon")

    def __init__(self, sample_metadata_fullpath: Path | None):
        self.sample_metadata_fullpath = sample_metadata_fullpath
        if sample_metadata_fullpath is None:
            self.exists = False
        else:
            self.exists = sample_metadata_fullpath.is_file()

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None and self.exists:
            assert self.sample_metadata_fullpath is not None
            self._df = pd.read_csv(self.sample_metadata_fullpath)
            self._df = self._df.rename(columns={"sample_name": "sample_id"})
        if self._df is None:
            msg = f"Could not find CSV Metadata file: {self.sample_metadata_fullpath}"
            raise FileNotFoundError(msg)
        return self._df

    def get_sample(self, sample_id: str) -> sampleMetadataCSVrecord | None:
        dfi = self.df[self.df.sample_id == sample_id]
        if len(dfi) == 1:
            rec = dfi.iloc[0].to_dict()
            return sampleMetadataCSVrecord.from_rec(rec)
        return None

    def get_all(
        self, available_samples: None | dict[str, str] = None
    ) -> sampleMetadata:

        if self.exists is False:
            return sampleMetadata()

        df = self.df
        if available_samples is not None:
            recs = [
                {"map_id": m, "sample_id": sid} for m, sid in available_samples.items()
            ]
            df_available = pd.DataFrame(recs)
            df = pd.merge(df_available, df, on="sample_id", how="left")
            df = df.drop("map_id", axis=1)
            df = df.drop_duplicates()

        recs = json.loads(df.to_json(orient="records"))

        fullrecords = [sampleMetadataCSVrecord.from_rec(rec) for rec in recs]
        return sampleMetadata(records=fullrecords, map_samples=available_samples)

    @property
    def columns(self) -> list[str]:
        cols = self.df.columns.to_list()
        if set(cols) != set(self.expected_cols):
            msg = "CSV columns do not match expected format"
            raise RuntimeError(msg)
        return cols

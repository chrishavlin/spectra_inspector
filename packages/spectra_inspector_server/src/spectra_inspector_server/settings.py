import os
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Spectra Inspector Server"
    spectra_inspector_data_root: str = os.environ.get(
        "SPECTRA_INSPECTOR_DATA_ROOT", "./"
    )
    spectra_inspector_host_data_root: str = os.environ.get(
        "SPECTRA_INSPECTOR_HOST_DATA_ROOT", "./"
    )

    spectra_inspector_allow_db_refresh: bool = False

    spectra_inspector_log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"

    @field_validator("spectra_inspector_log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        return v.upper()

    model_config = SettingsConfigDict(env_file=".env")

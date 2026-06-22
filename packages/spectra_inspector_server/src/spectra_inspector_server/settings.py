import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Spectra Inspector Server"
    spectra_inspector_data_root: str = os.environ.get(
        "SPECTRA_INSPECTOR_DATA_ROOT", "./"
    )
    spectra_inspector_host_data_root: str = os.environ.get(
        "SPECTRA_INSPECTOR_HOST_DATA_ROOT", "./"
    )

    model_config = SettingsConfigDict(env_file=".env")

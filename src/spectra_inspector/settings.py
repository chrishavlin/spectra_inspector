import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Spectra Inspector"
    write_dir: str = os.environ.get("SPECTRA_INSPECTOR_WRITE_DIR", "./")
    max_tmp_dirs: int = 100

    # connection info for the fastapi spectra_inspector_server. Not
    # currently being used, but still set here for now.
    server_host: str = "localhost"
    server_port: int = 8000

    # following used by the server submodule to find data
    spectra_inspector_data_root: str = os.environ.get(
        "SPECTRA_INSPECTOR_DATA_ROOT", "./"
    )

    # following only used by the docker build when mounting a volume
    # for the data.
    spectra_inspector_host_data_root: str = os.environ.get(
        "SPECTRA_INSPECTOR_HOST_DATA_ROOT", "./"
    )

    model_config = SettingsConfigDict(env_file=".env")

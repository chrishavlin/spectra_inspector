import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Spectra Inspector"
    write_dir: str = os.environ.get("SPECTRA_INSPECTOR_WRITE_DIR", "./")
    max_tmp_dirs: int = 100

    # connection info for the fastapi spectra_inspector_server
    server_host: str = "localhost"  # host.docker.internal
    server_port: int = 8000

    model_config = SettingsConfigDict(env_file=".env")

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Spectra Inspector"
    write_dir: str = os.environ.get("SPECTRA_INSPECTOR_WRITE_DIR", "./")
    max_tmp_dirs: int = 100

    model_config = SettingsConfigDict(env_file=".env")

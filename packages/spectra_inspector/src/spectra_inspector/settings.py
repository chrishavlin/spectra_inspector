from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = ".env"
ENV_PREFIX = "SPECTRA_INSPECTOR_"


class Settings(BaseSettings):
    # every field is read from the environment (or from ENV_FILE) with the
    # ENV_PREFIX prefix, e.g. app_name <- SPECTRA_INSPECTOR_APP_NAME. This
    # matches the prefix used by the spectra_inspector_server package.
    app_name: str = "Spectra Inspector"
    write_dir: str = "./"
    max_tmp_dirs: int = 100

    # connection info for the fastapi spectra_inspector_server
    server_host: str = "localhost"  # host.docker.internal
    server_port: int = 8000

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix=ENV_PREFIX)

    @model_validator(mode="before")
    @classmethod
    def _reject_unprefixed_env_file_keys(cls, values: Any) -> Any:
        # unprefixed keys are silently ignored by pydantic-settings, which would
        # leave a pre-prefix .env quietly falling back to the defaults below, so
        # point at them explicitly instead.
        env_file = Path(ENV_FILE)
        if env_file.is_file():
            unprefixed = sorted(
                key
                for key in dotenv_values(env_file)
                if key.lower() in cls.model_fields
            )
            if unprefixed:
                renames = ", ".join(f"{key} -> {ENV_PREFIX}{key}" for key in unprefixed)
                msg = (
                    f"{env_file} sets frontend options without the {ENV_PREFIX} "
                    f"prefix, which are no longer read. Rename them: {renames}"
                )
                raise ValueError(msg)
        return values

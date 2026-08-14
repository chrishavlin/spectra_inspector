from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import PositiveInt, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = ".env"
ENV_PREFIX = "SPECTRA_INSPECTOR_"


class Settings(BaseSettings):
    # every field is read from the environment (or from ENV_FILE) with the
    # ENV_PREFIX prefix, e.g. data_root <- SPECTRA_INSPECTOR_DATA_ROOT, matching
    # the spectra_inspector frontend package.
    app_name: str = "Spectra Inspector Server"
    data_root: str = "./"
    host_data_root: str = "./"

    allow_db_refresh: bool = False
    db_allow_mixed_basenames: bool = False

    # desktop_mode skips the (potentially very slow) recursive scan of data_root
    # at startup and instead enables the /browse-directory and
    # /datasets-in-directory endpoints so that a client can pick a working
    # directory to scan. Browsing is always confined to data_root.
    desktop_mode: bool = False

    # in desktop mode, stop a directory scan once this many datasets have been
    # found rather than walking the whole subtree. None means no limit. Ignored
    # when desktop_mode is false.
    max_datasets: PositiveInt | None = None

    # number of uvicorn workers that `fastapi run` starts with (only used by the
    # docker deployment, where the Dockerfile CMD expands it at container start)
    n_fastapi_workers: PositiveInt = 1

    log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix=ENV_PREFIX)

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="before")
    @classmethod
    def _reject_unprefixed_env_file_keys(cls, values: Any) -> Any:
        # unprefixed keys are silently ignored by pydantic-settings, which would
        # leave a pre-prefix .env quietly falling back to the defaults above, so
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
                    f"{env_file} sets server options without the {ENV_PREFIX} "
                    f"prefix, which are no longer read. Rename them: {renames}"
                )
                raise ValueError(msg)
        return values

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

    # directory of the on-disk store of data derived from the raw cubes, the
    # full-extent images and spectra (processor/derived_data.py). None means
    # everything is computed on request. compose bind-mounts the same host
    # path at the same path inside the container.
    derived_data_dir: str | None = None
    # whether the backend writes an entry it had to compute. False keeps the
    # store read-only: only the precompute script adds to it.
    derived_write_on_miss: bool = False
    # whether box and polygon spectra are answered from a sample's spectral
    # block pyramid when the store holds one (processor/pyramid.py). False
    # sums the cube for every region request, pyramids or not.
    derived_use_pyramids: bool = True

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

    # how many expensive operations (spectra, images) may wait for the single
    # pool worker before new ones are refused with a 503. One sample load fans
    # out a handful of image fetches at once, so this must comfortably exceed
    # a single user's burst. Every uvicorn worker holds its own queue, so the
    # effective cap is n_fastapi_workers * max_queued_ops.
    max_queued_ops: PositiveInt = 32

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

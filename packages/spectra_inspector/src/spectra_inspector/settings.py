from pathlib import Path
from typing import Annotated, Any

from dotenv import dotenv_values
from pydantic import NonNegativeInt, PositiveInt, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_FILE = ".env"
ENV_PREFIX = "SPECTRA_INSPECTOR_"


class Settings(BaseSettings):
    # every field is read from the environment (or from ENV_FILE) with the
    # ENV_PREFIX prefix, e.g. app_name <- SPECTRA_INSPECTOR_APP_NAME. This
    # matches the prefix used by the spectra_inspector_server package.
    app_name: str = "Spectra Inspector"
    write_dir: str = "./"
    max_tmp_dirs: int = 100

    # the image sizes the .zip summary export offers, as whole factors the map
    # is reduced by: 1 writes every map pixel, 2 half the width and height, and
    # so on. A comma separated list; the first entry is the one preselected,
    # so a deployment short on bandwidth can lead with a larger factor.
    export_scale_factors: Annotated[list[PositiveInt], NoDecode] = [2, 1]

    # connection info for the fastapi spectra_inspector_server
    # compose.yaml overrides this with the backend's service name in docker
    server_host: str = "localhost"
    server_port: int = 8000

    # how many image panels may be fetched at once when a page loads. The
    # fetches are what make the initial load slow, and a server running with
    # several workers answers them in parallel. Set to 1 to go back to fetching
    # them one after another.
    max_parallel_image_fetches: int = 4

    # desktop_mode exposes the working-directory picker on the data selection
    # and inspector pages. It requires the server to run with
    # SPECTRA_INSPECTOR_DESKTOP_MODE=true as well: the picker drives the
    # server's /browse-directory and /datasets-in-directory endpoints, which
    # are disabled otherwise.
    desktop_mode: bool = False

    # desktop mode only: seconds without mouse or keyboard input before the
    # "still working?" overlay is raised (components/inactivity_guard.py).
    # 0 turns it off.
    inactivity_timeout_seconds: NonNegativeInt = 1800

    # gunicorn worker processes the docker image starts; only the Dockerfile
    # CMD reads it (serve.py runs the flask development server instead)
    n_frontend_workers: PositiveInt = 2

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_prefix=ENV_PREFIX)

    @field_validator("export_scale_factors", mode="before")
    @classmethod
    def _split_scale_factors(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("export_scale_factors")
    @classmethod
    def _distinct_scale_factors(cls, value: list[int]) -> list[int]:
        if not value or len(set(value)) != len(value):
            msg = "export_scale_factors needs at least one factor, each given once"
            raise ValueError(msg)
        return value

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

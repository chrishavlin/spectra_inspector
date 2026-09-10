# based off https://github.com/astral-sh/uv-docker-example

# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# need
# gcc and python dev headers (for dependencies that get compiled)
# git for runtime version resolution
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    python3-dev

# Setup a non-root user
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Omit development dependencies
ENV UV_NO_DEV=1

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Number of uvicorn workers to run. Overridable at run time (docker compose
# passes through the value from the frontend `.env` file).
ENV SPECTRA_INSPECTOR_N_FASTAPI_WORKERS=1

# Use the non-root user to run our application
USER nonroot

# Run the FastAPI application by default. The venv's bin is on PATH, so call
# `fastapi` directly rather than through `uv run`: `uv run` re-syncs the
# environment on every start, which fails as the non-root user because the venv
# is owned by root. `--host 0.0.0.0` allows access from outside the container.
# `sh -c` so the worker count is expanded at container start; `exec` so the
# server is PID 1 and receives compose's stop signal.
CMD ["sh", "-c", "exec fastapi run --workers ${SPECTRA_INSPECTOR_N_FASTAPI_WORKERS} --host 0.0.0.0 src/spectra_inspector_server/main.py"]

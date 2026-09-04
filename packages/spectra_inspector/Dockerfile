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

# Number of gunicorn worker processes. Overridable at run time (docker compose
# passes the frontend .env through to the container).
ENV SPECTRA_INSPECTOR_N_FRONTEND_WORKERS=2

# Use the non-root user to run our application
USER nonroot

# Serve the dash app's flask server with gunicorn. Callbacks mostly wait on the
# backend over HTTP, so threads per worker cover the browser's parallel image
# fetches; the timeout outlasts the backend's two minute operation limit.
# compose.override.yaml replaces this with the flask development server for
# development. `sh -c` so the worker count is expanded at container start.
CMD ["sh", "-c", "uv run gunicorn --workers ${SPECTRA_INSPECTOR_N_FRONTEND_WORKERS} --threads 4 --worker-class gthread --timeout 180 --bind 0.0.0.0:8050 --access-logfile - spectra_inspector.main:server"]

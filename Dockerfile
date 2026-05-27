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

# we need chrome for dash's figure export for now. ugh. i'm sorry.
# first deps are cause we want a browser on a slim OS image, second runs kaleido's chrome installer
# it triggers some warnings about ubuntu and get_browser() but seems to work ok.
RUN apt-get install -y --no-install-recommends libnss3 libatk-bridge2.0-0 libcups2 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2
RUN --mount=type=cache,target=/root/.cache/uv uv run kaleido_get_chrome

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Use the non-root user to run our application
USER nonroot

# need a wsgi server.... but for now:
CMD ["uv", "run", "python", "serve.py", "--host", "0.0.0.0", "--port", "8050"]

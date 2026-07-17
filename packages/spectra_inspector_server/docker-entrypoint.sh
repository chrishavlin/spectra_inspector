#!/bin/sh
exec uv run fastapi run --host 0.0.0.0 --workers "${SPECTRA_INSPECTOR_DOCKER_FASTAPI_WORKERS:-1}" src/spectra_inspector_server/main.py

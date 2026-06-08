#!/bin/bash
set -a
# shellcheck source=/dev/null
source packages/spectra_inspector/.env
# shellcheck source=/dev/null
source packages/spectra_inspector_server/.env
docker compose build
docker compose up

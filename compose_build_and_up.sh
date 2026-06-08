#!/bin/bash
set -a
# shellcheck source=/dev/null
source packages/spectra_insepctor/.env
# shellcheck source=/dev/null
source packages/spectra_insepctor_server/.env
docker compose build
docker compose up

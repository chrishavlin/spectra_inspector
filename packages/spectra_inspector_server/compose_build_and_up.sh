#!/bin/bash
set -a
# shellcheck source=/dev/null
source .env
docker compose build
docker compose up

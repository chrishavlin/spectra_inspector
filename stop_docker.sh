#!/usr/bin/env bash
# Stop and remove the containers started by start_docker.sh. Images and the
# data directory are left alone.
#
#   ./stop_docker.sh          stop a development stack
#   ./stop_docker.sh prod     stop a deployment stack
set -euo pipefail
cd "$(dirname "$0")"

mode="${1:-dev}"
compose=(
    docker compose
    --env-file packages/spectra_inspector/.env
    --env-file packages/spectra_inspector_server/.env
)

case "$mode" in
    dev) ;;
    prod)
        compose+=(-f compose.yaml -f compose.prod.yaml)
        ;;
    *)
        echo "usage: $0 [dev|prod]" >&2
        exit 2
        ;;
esac

"${compose[@]}" down

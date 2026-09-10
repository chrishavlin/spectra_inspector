#!/usr/bin/env bash
# Run `docker compose` with this repository's configuration filled in.
#
#   ./compose.sh <compose args>          development stack (compose.override.yaml)
#   ./compose.sh prod <compose args>     deployment stack (compose.prod.yaml)
#
#   ./compose.sh ps
#   ./compose.sh prod logs -f caddy
#   ./compose.sh prod restart caddy
#
# Both packages' .env files are passed with --env-file so compose can
# interpolate the ${...} references in compose.yaml (the data-root bind mount);
# a bare `docker compose` stops with "required variable ... is missing a value".
# start_docker.sh and stop_docker.sh build on this script.
set -euo pipefail
cd "$(dirname "$0")"

frontend_env=packages/spectra_inspector/.env
server_env=packages/spectra_inspector_server/.env

for env_file in "$frontend_env" "$server_env"; do
    if [ ! -f "$env_file" ]; then
        echo "missing $env_file: copy the defaults.env next to it and edit" >&2
        exit 1
    fi
done

compose=(docker compose --env-file "$frontend_env" --env-file "$server_env")

case "${1:-}" in
    prod)
        shift
        compose+=(-f compose.yaml -f compose.prod.yaml)
        ;;
    dev)
        shift
        ;;
esac

exec "${compose[@]}" "$@"

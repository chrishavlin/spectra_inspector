#!/usr/bin/env bash
# Build and start the app with docker compose.
#
#   ./start_docker.sh         development (default): foreground, dash debugger
#                             and reloader on, frontend on port 8050 of every
#                             interface, API docs on http://127.0.0.1:8000/docs
#   ./start_docker.sh prod    deployment: detached, restarts on failure and
#                             after a reboot, frontend on 127.0.0.1:8050 only,
#                             backend not published at all
#
# Both packages' .env files must exist (README: "Initialize configuration").
# They are passed to compose for ${...} interpolation and handed to the
# containers, so editing one and re-running this script is enough to apply it.
set -euo pipefail
cd "$(dirname "$0")"

mode="${1:-dev}"
frontend_env=packages/spectra_inspector/.env
server_env=packages/spectra_inspector_server/.env

for env_file in "$frontend_env" "$server_env"; do
    if [ ! -f "$env_file" ]; then
        echo "missing $env_file: copy the defaults.env next to it and edit" >&2
        exit 1
    fi
done

compose=(docker compose --env-file "$frontend_env" --env-file "$server_env")

case "$mode" in
    dev)
        "${compose[@]}" up --build
        ;;
    prod)
        compose+=(-f compose.yaml -f compose.prod.yaml)
        "${compose[@]}" up --build --detach
        "${compose[@]}" ps
        echo "frontend listening on 127.0.0.1:8050 (loopback only)."
        echo "logs: docker compose logs -f    stop: ./stop_docker.sh prod"
        ;;
    *)
        echo "usage: $0 [dev|prod]" >&2
        exit 2
        ;;
esac

#!/usr/bin/env bash
# Build and start the app with docker compose.
#
#   ./start_docker.sh         development (default): foreground, dash debugger
#                             and reloader on, frontend on port 8050 of every
#                             interface, API docs on http://127.0.0.1:8000/docs
#   ./start_docker.sh prod    deployment: detached, restarts on failure and
#                             after a reboot, the caddy reverse proxy on ports
#                             80/443 is the only thing published
#
# Both packages' .env files must exist (README: "Initialize configuration").
# They are passed to compose for ${...} interpolation and handed to the
# containers, so editing one and re-running this script is enough to apply it.
# Deployment also needs proxy/Caddyfile (copied from proxy/Caddyfile.example);
# see DEPLOYMENT.md.
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
        if [ ! -f proxy/Caddyfile ]; then
            echo "missing proxy/Caddyfile: copy proxy/Caddyfile.example and edit" >&2
            exit 1
        fi
        compose+=(-f compose.yaml -f compose.prod.yaml)
        "${compose[@]}" up --build --detach
        "${compose[@]}" ps
        echo "caddy listening on ports 80 and 443 for the site named in proxy/Caddyfile."
        echo "stop: ./stop_docker.sh prod"
        echo "any other compose command needs the same flags, e.g. to follow the logs:"
        echo "  ${compose[*]} logs -f"
        ;;
    *)
        echo "usage: $0 [dev|prod]" >&2
        exit 2
        ;;
esac

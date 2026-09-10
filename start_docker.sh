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
# see DEPLOYMENT.md. Any other compose command against either stack goes
# through ./compose.sh [prod] ..., which supplies the same flags.
set -euo pipefail
cd "$(dirname "$0")"

mode="${1:-dev}"

case "$mode" in
    dev)
        ./compose.sh up --build
        ;;
    prod)
        if [ ! -f proxy/Caddyfile ]; then
            echo "missing proxy/Caddyfile: copy proxy/Caddyfile.example and edit" >&2
            exit 1
        fi
        ./compose.sh prod up --build --detach
        ./compose.sh prod ps
        echo "caddy listening on ports 80 and 443 for the site named in proxy/Caddyfile."
        echo "logs: ./compose.sh prod logs -f    stop: ./stop_docker.sh prod"
        ;;
    *)
        echo "usage: $0 [dev|prod]" >&2
        exit 2
        ;;
esac

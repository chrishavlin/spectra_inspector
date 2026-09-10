#!/usr/bin/env bash
# Stop and remove the containers started by start_docker.sh. Images, the data
# directory and the caddy volumes (the TLS certificate) are left alone.
#
#   ./stop_docker.sh          stop a development stack
#   ./stop_docker.sh prod     stop a deployment stack
set -euo pipefail
cd "$(dirname "$0")"

mode="${1:-dev}"

case "$mode" in
    dev | prod)
        ./compose.sh "$mode" down
        ;;
    *)
        echo "usage: $0 [dev|prod]" >&2
        exit 2
        ;;
esac

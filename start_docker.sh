#!/bin/bash
docker compose --env-file packages/spectra_inspector/.env --env-file packages/spectra_inspector_server/.env build
docker compose --env-file packages/spectra_inspector/.env --env-file packages/spectra_inspector_server/.env up

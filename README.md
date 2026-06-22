# spectra_inspector

## Deployment

### Initialize data

### Running via Docker

#### Initialize environment variables

#### Build with docker compose

The following helper script will load in environment variables, build the
containers and spin them up:

`./compose_build_and_up.sh`

### Running via uv

#### Initialize environment variables

#### Initialize uv environment:

From top level,

```
uv sync
```

#### Start the server and frontend:

Terminal 1:

```shell
cd packages/spectra_inspector_server
uv run fastapi run src/spectra_inspector_server/main.py
```

Terminal 2:

```shell
cd packages/spectra_inspector
uv run python serve.py
```

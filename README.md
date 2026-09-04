# spectra_inspector

A Dash/Plotly frontend and FastAPI backend for inspecting and subsampling EDAX
datasets.

## Initialize configuration

Before running either Docker or a local development environment, create the
environment files for the two packages.

### Frontend package

From the repository root, copy the frontend defaults to a local `.env` file:

```sh
cp packages/spectra_inspector/defaults.env packages/spectra_inspector/.env
```

Then edit `packages/spectra_inspector/.env` and set the frontend values you
need. Every frontend setting is read with a `SPECTRA_INSPECTOR_` prefix
(case-insensitive from the environment):

- `SPECTRA_INSPECTOR_APP_NAME`: display name used by the app. Defaults to
  `Spectra Inspector`.
- `SPECTRA_INSPECTOR_WRITE_DIR`: writable directory for temporary download
  files. Defaults to the current working directory.
- `SPECTRA_INSPECTOR_MAX_TMP_DIRS`: maximum number of temporary directories to
  keep before cleanup begins. Defaults to `100`.
- `SPECTRA_INSPECTOR_SERVER_HOST`: host name or address of the FastAPI backend
  used by the frontend. Defaults to `localhost`.
- `SPECTRA_INSPECTOR_SERVER_PORT`: port number of the FastAPI backend used by
  the frontend. Defaults to `8000`.
- `SPECTRA_INSPECTOR_DESKTOP_MODE`: set to `true` to show the working-directory
  picker on the data selection and inspector pages. Defaults to `false`. The
  backend must be started with `SPECTRA_INSPECTOR_DESKTOP_MODE=true` as well;
  see [Configuration for local deployment](#configuration-for-local-deployment).

These names gained the `SPECTRA_INSPECTOR_` prefix in a later release; an
existing `.env` still using the unprefixed spellings (`WRITE_DIR`,
`SERVER_HOST`, ...) raises a startup error naming the keys to rename.

### Backend package

Create the backend environment file from the packaged defaults:

```sh
cp packages/spectra_inspector_server/defaults.env packages/spectra_inspector_server/.env
```

Then edit `packages/spectra_inspector_server/.env` and set the data paths and
runtime options for your environment. As with the frontend, every backend
setting is read with a `SPECTRA_INSPECTOR_` prefix:

- `SPECTRA_INSPECTOR_APP_NAME`: display name used by the backend service.
  Defaults to `Spectra Inspector Server`.
- `SPECTRA_INSPECTOR_DATA_ROOT`: root directory that the backend scans
  recursively for EDAX datasets. Defaults to `./`. When running in docker, this
  is the **container** directory name (which gets binded to
  `SPECTRA_INSPECTOR_HOST_DATA_ROOT`) and can have any name.
- `SPECTRA_INSPECTOR_HOST_DATA_ROOT`: host-machine directory to bind-mount into
  the Docker container when using Docker Compose. Defaults to `./`. Only used by
  docker compose.
- `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH`: set to `true` to allow the local
  database to refresh from disk when the service starts. Defaults to `false`.
- `SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES`: set to `true` to additionally
  detect datasets whose files do **not** all share a basename, pairing
  `map*_0.spd`/`.spc`/`.xml` with the first `fov*.ipr`/`.bmp` in the same
  directory. Defaults to `false`. See the backend README for the caveats.
- `SPECTRA_INSPECTOR_DESKTOP_MODE`: set to `true` to skip the recursive scan of
  `SPECTRA_INSPECTOR_DATA_ROOT` at startup and instead let the frontend pick a
  working directory to scan. Defaults to `false`. See
  [Configuration for local deployment](#configuration-for-local-deployment).
- `SPECTRA_INSPECTOR_N_FASTAPI_WORKERS`: number of uvicorn workers that the
  FastAPI backend starts with. Defaults to `1`. Only used by the docker
  deployment, where docker compose passes the value through to the backend
  container.
- `SPECTRA_INSPECTOR_LOG_LEVEL`: logging verbosity for the backend. Accepted
  values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`; the default is
  `INFO`.

`APP_NAME` gained the `SPECTRA_INSPECTOR_` prefix along with the frontend keys;
the other backend names are unchanged. An existing `.env` still using an
unprefixed spelling raises a startup error naming the key to rename.

### Configuration for local deployment

When serving as a desktop app:

- set `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH=true` in
  `packages/spectra_inspector_server/.env` to refresh the available files from
  the frontend. Set to false for production deployments (this can be an
  expensive step).
- set `SPECTRA_INSPECTOR_DESKTOP_MODE=true` in **both** `.env` files when the
  data root holds more datasets than are usable in one sample dropdown, or when
  scanning all of it at startup is too slow.

  In desktop mode the backend does not scan `SPECTRA_INSPECTOR_DATA_ROOT` at
  startup. Instead it exposes two endpoints — `/browse-directory` and
  `/datasets-in-directory` — that the frontend's working-directory picker uses
  to walk the tree and scan one directory on demand. Both endpoints reject any
  path that resolves outside of `SPECTRA_INSPECTOR_DATA_ROOT` (including via
  symlinks), and both return `403` when desktop mode is off, so the data root is
  still the boundary of what a client can reach.

  Until a directory is picked, the backend reports no available datasets. The
  scan replaces the previous working set, so the sample dropdown, the sample map
  and the loadable sample names always describe the selected directory alone.
  "Include subdirectories" controls whether the scan recurses; leave it on
  unless a single directory holds everything you need.

  Both packages read the setting independently: with it on in the frontend only,
  the picker appears but every request it makes is refused; with it on in the
  backend only, nothing scans and no picker is offered to select a directory.

## Running via Docker

The repository includes OS-specific helper scripts that build the Docker Compose
services and pass both `.env` files to Compose. Each takes an optional mode,
`dev` (the default) or `prod`:

- macOS/Linux:

  ```sh
  ./start_docker.sh          # development
  ./start_docker.sh prod     # deployment
  ./stop_docker.sh [prod]    # stop and remove the containers
  ```

- Windows PowerShell:

  ```powershell
  ./start_docker.ps1 [prod]
  ./stop_docker.ps1 [prod]
  ```

- Windows Command Prompt:

  ```bat
  start_docker.bat [prod]
  stop_docker.bat [prod]
  ```

The `.env` files serve two purposes: Compose interpolates the `${...}`
references in the compose files from them (the data-root bind mount), and it
hands them to the containers as environment. They are not baked into the images,
so a configuration change only needs the stack restarted, not rebuilt. Inside
docker the frontend always reaches the backend by its service name over the
compose network, so `SPECTRA_INSPECTOR_SERVER_HOST`/`_PORT` and
`SPECTRA_INSPECTOR_WRITE_DIR` from the frontend `.env` are overridden. The data
root is mounted read-only.

### Development mode

`compose.yaml` holds the service definitions and `compose.override.yaml`, which
`docker compose` loads automatically, adds the development settings: the
containers run as root with the dev dependencies, the Dash debugger and reloader
are on, and `docker compose watch` syncs edits into the running containers. The
app is available at http://localhost:8050 (published on every interface, so it
can be checked from another device) and the API docs at
http://127.0.0.1:8000/docs (loopback only; the frontend does not use this port).

On windows, you may need to go to http://127.0.0.1:8050 instead of `localhost`.

### Deployment mode

`prod` layers `compose.prod.yaml` on `compose.yaml` instead and starts the stack
detached:

```sh
docker compose --env-file packages/spectra_inspector/.env \
               --env-file packages/spectra_inspector_server/.env \
               -f compose.yaml -f compose.prod.yaml up --build --detach
```

- The only host endpoint is the frontend on `127.0.0.1:8050`. The backend is not
  published at all; the frontend reaches it over the compose network. A reverse
  proxy on the host is expected to terminate TLS (and provide authentication,
  the app has none) and forward to `http://127.0.0.1:8050`. Allow a proxy read
  timeout of at least 180 s (backend operations may run for two minutes) and
  request bodies of tens of MB (Dash callbacks upload the figure state).
- Both containers run as the image's non-root user with the Dash debugger off,
  restart on failure and after a host reboot (`restart: unless-stopped`; the
  docker daemon must itself be enabled at boot), and cap their json log files.
- The backend has a health check against `/info`; the frontend waits for it.
  `docker compose ps` shows the state, `docker compose logs -f` follows both
  services' logs.

Set `SPECTRA_INSPECTOR_N_FASTAPI_WORKERS` in the backend `.env` to run more than
one uvicorn worker.

## Running via uv

### Initialize the Python environment

From the repository root:

```sh
uv sync
```

### Start the server and frontend

Terminal 1:

```sh
cd packages/spectra_inspector_server
uv run fastapi run src/spectra_inspector_server/main.py
```

Terminal 2:

```sh
cd packages/spectra_inspector
uv run python serve.py
```

### Start both in the background (Windows)

`start_uv_local.bat` starts both processes from a single Command Prompt. Each
one runs in its own minimized console window, so they keep running after the
window you launched them from is closed, and each writes its output to a log
file under `logs\` in the repository root:

```bat
start_uv_local.bat
```

The frontend is started with `--debug 0`, so the Dash reloader and the Werkzeug
debugger are off; start it by hand as above when you want them.

The backend starts with 4 uvicorn workers; pass a different count as the only
argument:

```bat
start_uv_local.bat 8
```

Stop both services with:

```bat
stop_uv_local.bat
```

The processes survive a remote desktop disconnect but not a log off; for a
service that outlives the login session, register the commands as a Windows
service or a scheduled task instead.

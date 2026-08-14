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
- `SPECTRA_INSPECTOR_N_FASTAPI_WORKERS`: number of uvicorn workers that the
  FastAPI backend starts with. Defaults to `1`. Only used by the docker
  deployment, where docker compose passes the value through to the backend
  container.
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
services and pass both `.env` files to Compose.

- macOS/Linux:

  ```sh
  ./start_docker.sh
  ```

- Windows PowerShell:

  ```powershell
  ./start_docker.ps1
  ```

- Windows Command Prompt:

  ```bat
  start_docker.bat
  ```

These scripts run `docker compose` with both environment files so the frontend
and backend pick up the correct configuration. After startup, the app should be
available at http://localhost:8050 and the API docs at
http://localhost:8000/docs.

On windows, you may need to go to http://127.0.0.1:8050 and
http://127.0.0.1:8000/docs .

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

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
need. The frontend settings module reads the following configuration values
(case-insensitive from the environment):

- `APP_NAME`: display name used by the app. Defaults to `Spectra Inspector`.
- `WRITE_DIR` (also accepted as `SPECTRA_INSPECTOR_WRITE_DIR` by the settings
  code): writable directory for temporary download files. Defaults to the
  current working directory.
- `MAX_TMP_DIRS`: maximum number of temporary directories to keep before cleanup
  begins. Defaults to `100`.
- `SERVER_HOST`: host name or address of the FastAPI backend used by the
  frontend. Defaults to `localhost`.
- `SERVER_PORT`: port number of the FastAPI backend used by the frontend.
  Defaults to `8000`.

### Backend package

Create the backend environment file from the packaged defaults:

```sh
cp packages/spectra_inspector_server/defaults.env packages/spectra_inspector_server/.env
```

Then edit `packages/spectra_inspector_server/.env` and set the data paths and
runtime options for your environment. The backend settings module reads these
values:

- `APP_NAME`: display name used by the backend service. Defaults to
  `Spectra Inspector Server`.
- `SPECTRA_INSPECTOR_DATA_ROOT`: root directory that the backend scans
  recursively for EDAX datasets. Defaults to `./`. When running in docker, this
  is the **container** directory name (which gets binded to
  `SPECTRA_INSPECTOR_HOST_DATA_ROOT`) and can have any name.
- `SPECTRA_INSPECTOR_HOST_DATA_ROOT`: host-machine directory to bind-mount into
  the Docker container when using Docker Compose. Defaults to `./`. Only used by
  docker compose.
- `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH`: set to `true` to allow the local
  database to refresh from disk when the service starts. Defaults to `false`.
- `SPECTRA_INSPECTOR_LOG_LEVEL`: logging verbosity for the backend. Accepted
  values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`; the default is
  `INFO`.

### Configuration for local deployment

When serving as a desktop app:

- set `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH=true` in
  `packages/spectra_inspector_server/.env` to refresh the available files from
  the frontend. Set to false for production deployments (this can be an
  expensive step).

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

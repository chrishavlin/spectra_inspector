# spectra_inspector

A dash-plotly web app for subsampling EDAX filesets

# Developer notes

## Environment variables

Set in `.env`:

- `WRITE_DIR`='/path/to/a/writeable/directory' occasionally cleared by the
  frontend, used for storing temp files provided as downloads to user. When
  running in docker, should be set to a folder at the root level like
  `/tmp_writes`.
- `MAX_TMP_DIRS`=100 max number of tmp directories before they start clearing

- `SPECTRA_INSPECTOR_DATA_ROOT`='/path/to/data' . When running locally this is
  just the path to the top level of the data directories. When running in
  docker, this is the path on the container to look for data. Docker will mount
  a volume to this path.
- `SPECTRA_INSPECTOR_HOST_DATA_ROOT`='path/to/data/on/host' . ONLY used by
  Docker. This directory gets mounted as a volume to the container path set by
  `SPECTRA_INSPECTOR_DATA_ROOT`

#### not used right now

a couple of settings are still around ised when running a separate server for
backend data processing. These are not currently used.

- `SERVER_HOST`=host to use. Use "host.docker.internal" for deployment when the
  `spectra_inspector_server` is running via docker on the same machine.
- `SERVER_PORT`=port to access `spectra_inspector_server` api on

## Running locally

### example local .env

For running locally, here's what a `.env` might look like:

```
MAX_TMP_DIRS=10
WRITE_DIR='/path/to/writeable/dir/tmp_writes'
SPECTRA_INSPECTOR_DATA_ROOT = '/path/to/data/directory'
```

### run the dash app

```
uv sync --group dev
uv run python serve.py
```

## Building and Running Docker Containers

### example docker .env

For running with docker, here's what a `.env` might look like:

```

# docker
WRITE_DIR='/tmp_writes'
SPECTRA_INSPECTOR_HOST_DATA_ROOT='/path/to/data/directory/on/host/machine'
SPECTRA_INSPECTOR_DATA_ROOT='/TorresData'
```

### Building and running locally

If you just want to build and run for testing purposes,

```
./compose_build_and_up.sh`
```

will set all the `.env` variables then build and spin up the docker container in
the foreground.

To just build:

```
set -a
source .env
docker compose build
```

To detach the container and run in background after building

```
docker compose up -d
```

## Credits

Initial multi-page dash template modified from
https://github.com/open-resources/dash_curriculum

# spectra_inspector_server

The `spectra_inspector_server` is the backend FastAPI server for the
[`spectra_inspector`](https://github.com/chrishavlin/spectra_inspector)
dashboard. The `spectra_inspector_server` includes endpoints for inspecting and
subsampling EDAX filesets. Data IO relis on Hyperspy's
[RosettaSciIO](https://hyperspy.org/rosettasciio/) package and at present is
limited to a local file system database of uniquely named EDAX filesets.

[![Actions Status][actions-badge]][actions-link]
[![Documentation Status][rtd-badge]][rtd-link]
[![PyPI version][pypi-version]][pypi-link]
[![PyPI platforms][pypi-platforms]][pypi-link]
[![GitHub Discussion][github-discussions-badge]][github-discussions-link]

## Developer Notes

### Local Setup

Environment setup, install

```
uv venv
source .venv/bin/activate
uv pip install -e .
```

To start the fastapi server in a dev environment:

```
fastapi run src/spectra_inspector_server/main.py
```

Visit http://0.0.0.0:8000/docs to check the API, test calls via browser.

### Production setup

Notes on serving in a production environment, see
https://fastapi.tiangolo.com/deployment/

### Data Setup - Local Filesystem Database

At present, file operations (listing available datasets, sampling a dataset)
require a local filesystem database containing EDAX file sets. On initial app
run, the top level root directory specified by the `SPECTRA_INSPECTOR_DATA_ROOT`
will be recursively traversed to identify existing EDAX file sets. A file set is
given by a common root name with a number of expected files:

```shell
basename.spd
basename.spc
basename.ipr
basename.bmp
basename.xml
```

- all files must be present for a file set to be added to the available
  datasets.
- file basenames must be unique across directories
- filesets may reside in any nested file structure (to the recursion limit of
  python)

### Configuration

Copy `default.env` to `.env` and modify as needed. Some defaults may be set by
environment variables as well, with preference given to the values in `.env`.

#### `SPECTRA_INSPECTOR_DATA_ROOT`

When using a local filesystem repository, the top-level directory of the
directory to search recursively for EDAX file sets. When not set in `.env`, the
default value will be detected from a standard environment variable of the same
name and if not found, will default to `./`.

### manual type checking

```
uv sync --group typing
uv run ty check
```

### Deployment

To build and run (and load env vars from `.env`)

```
$ ./compose_build_and_up.sh
```

Env vars:

- `SPECTRA_INSPECTOR_DATA_ROOT`: path to data used by fastapi server. If running
  in docker, this should point to the mounted volume path, not the host data
  path. If running outside of docker, this should point to the host data path.
- `SPECTRA_INSPECTOR_HOST_DATA_ROOT`: path to data on host machine, used by
  docker compose to bind mount a directory. Only used by docker.

So an example `.env` for deployment might look like:

```
SPECTRA_INSPECTOR_DATA_ROOT='/TorresSamplesFromBox'
SPECTRA_INSPECTOR_HOST_DATA_ROOT='/path/to/host/TorresSamplesFromBox'
```

<!-- SPHINX-START -->

<!-- prettier-ignore-start -->
[actions-badge]:            https://github.com/chrishavlin/spectra_inspector_server/workflows/CI/badge.svg
[actions-link]:             https://github.com/chrishavlin/spectra_inspector_server/actions
[github-discussions-badge]: https://img.shields.io/static/v1?label=Discussions&message=Ask&color=blue&logo=github
[github-discussions-link]:  https://github.com/chrishavlin/spectra_inspector_server/discussions
[pypi-link]:                https://pypi.org/project/spectra_inspector_server/
[pypi-platforms]:           https://img.shields.io/pypi/pyversions/spectra_inspector_server
[pypi-version]:             https://img.shields.io/pypi/v/spectra_inspector_server
[rtd-badge]:                https://readthedocs.org/projects/spectra_inspector_server/badge/?version=latest
[rtd-link]:                 https://spectra_inspector_server.readthedocs.io/en/latest/?badge=latest

<!-- prettier-ignore-end -->

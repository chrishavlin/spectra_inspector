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

- the `.spd`, `.spc` and `.ipr` must be present for a file set to be added to
  the available datasets; the `.bmp` and `.xml` are optional.
- file sets are keyed by basename, so basenames should be unique across
  directories: when the same basename is found a second time, the later file set
  is skipped with a warning and only the first one found is available. Enabling
  `SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES` (see below) keys by full path
  instead, avoiding the collision entirely.
- filesets may reside in any nested file structure (to the recursion limit of
  python)

With `SPECTRA_INSPECTOR_DESKTOP_MODE` enabled the traversal is deferred: the
client picks one directory below the data root to scan instead (see below).

### Configuration

Copy `default.env` to `.env` and modify as needed. Every setting is read with a
`SPECTRA_INSPECTOR_` prefix (`SPECTRA_INSPECTOR_APP_NAME`,
`SPECTRA_INSPECTOR_DATA_ROOT`, `SPECTRA_INSPECTOR_HOST_DATA_ROOT`,
`SPECTRA_INSPECTOR_ALLOW_DB_REFRESH`,
`SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES`, `SPECTRA_INSPECTOR_DESKTOP_MODE`,
`SPECTRA_INSPECTOR_MAX_DATASETS`, `SPECTRA_INSPECTOR_N_FASTAPI_WORKERS`,
`SPECTRA_INSPECTOR_LOG_LEVEL`), matching the `spectra_inspector` frontend
package. The same names may be set as process environment variables instead,
with preference given to the values in `.env`.

Unknown keys in `.env` are rejected rather than ignored, so a stale `.env` fails
fast: keys under the prefix that don't match a setting raise `extra_forbidden`,
and unprefixed spellings (`APP_NAME`, ...) raise an error listing their new
names.

#### `SPECTRA_INSPECTOR_DATA_ROOT`

When using a local filesystem repository, the top-level directory of the
directory to search recursively for EDAX file sets. When set in neither `.env`
nor the environment, defaults to `./`.

#### `SPECTRA_INSPECTOR_DB_ALLOW_MIXED_BASENAMES`

Defaults to `false`. By default a file set is detected only when its files all
share a basename (`sample.spd`, `sample.spc`, `sample.ipr`, and optionally
`sample.bmp`/`sample.xml`).

Set to `true` to _additionally_ detect sets whose files do not share a basename,
as produced by some acquisition setups: within a single directory, each
`map*_0.spd` is paired with the matching `map*_0.spc` and `map*_0.xml`, and with
the first (alphabetically sorted) `fov*.ipr` plus the first `fov*.bmp` if one is
present. Two consequences worth knowing:

- these sets require the `.xml`, whereas common-basename sets treat it as
  optional, and every map in a directory shares that directory's one `fov`
  image.
- with this enabled, datasets are keyed by the full `.spd` path rather than by
  basename, so basenames no longer need to be unique across the data root.

Common-basename detection still runs either way, so turning this on only adds
datasets.

#### `SPECTRA_INSPECTOR_DESKTOP_MODE`

Defaults to `false`. Set to `true` for desktop deployments where
`SPECTRA_INSPECTOR_DATA_ROOT` is large enough that the startup scan is too slow
or that the resulting list of datasets is unusable in a single dropdown.

With it enabled:

- the recursive scan of the data root at startup is skipped, so the server
  reports no available datasets until a client selects a working directory.
- `GET /browse-directory?path=<relative>` lists the subdirectories of one
  directory, along with the number of EDAX file sets found directly in it.
  Hidden directories (leading `.`) are omitted.
- `GET /datasets-in-directory?path=<relative>&recursive=<bool>` scans that
  directory and makes it the working set, replacing whatever the database held
  before. The response is the same `AvailableDatasets` payload as
  `/available-datasets`, plus the `directory` that produced it.
- `/available-datasets?refresh_db=true` re-scans the working directory rather
  than the whole data root (and does nothing until one is selected), so a
  refresh stays as cheap as the scan the client already asked for.

Paths on the wire are posix and relative to the data root, with `""` meaning the
data root itself. Every one is resolved (following symlinks) and checked against
the data root before use: anything landing outside gets a `403`, as does either
endpoint when desktop mode is off. Unlike the startup scan, a directory holding
a duplicate basename is logged and skipped rather than raising, and unreadable
directories are skipped instead of aborting the scan.

#### `SPECTRA_INSPECTOR_MAX_DATASETS`

Unset by default, meaning no limit. When set to a positive integer _and_
`SPECTRA_INSPECTOR_DESKTOP_MODE` is enabled, a directory scan stops as soon as
that many datasets have been registered instead of walking the rest of the
subtree, keeping the dataset dropdown and the scan itself bounded when a client
selects a directory holding far more data than it can usefully display.

The datasets kept are whichever the traversal reaches first (a directory's own
file sets before its subdirectories, both in sorted order), so the cap truncates
rather than selects. The setting is ignored entirely when desktop mode is off,
where the startup scan of the whole data root is still exhaustive.

A truncated scan is reported as `truncated: true` on the `AvailableDatasets`
payload (and logged at `INFO`), so a client can tell a partial listing from a
complete one. The flag describes the most recent scan and is served by
`/available-datasets` as well, since that endpoint returns whatever working set
the last scan produced. There is no count of what was skipped: the traversal
stops at the limit rather than finishing and counting. The frontend's directory
picker turns the flag into a warning next to the sample dropdown.

### manual type checking

```
uv sync --group typing
uv run ty check
```

### Deployment

To build and run with docker compose (loading env vars from both packages'
`.env` files), from the repository root:

```
$ ./start_docker.sh          # development
$ ./start_docker.sh prod     # deployment, see the root README
```

Env vars:

- `SPECTRA_INSPECTOR_DATA_ROOT`: path to data used by fastapi server. If running
  in docker, this should point to the mounted volume path, not the host data
  path. If running outside of docker, this should point to the host data path.
- `SPECTRA_INSPECTOR_HOST_DATA_ROOT`: path to data on host machine, used by
  docker compose to bind mount a directory. Only used by docker.
- `SPECTRA_INSPECTOR_N_FASTAPI_WORKERS`: number of uvicorn workers that
  `fastapi run` starts with, defaults to `1`. Only used by docker: docker
  compose passes it through to the container, where the `Dockerfile` `CMD`
  expands it at start up.

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

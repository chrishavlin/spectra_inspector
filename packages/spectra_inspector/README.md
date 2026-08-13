# spectra_inspector

A dash-plotly web app for subsampling EDAX filesets

# Developer notes

## Deployment - Docker

### environment variables

Set in `.env` (see `defaults.env` for a starting point). Every setting this
package reads is prefixed with `SPECTRA_INSPECTOR_`, matching the
`spectra_inspector_server` package:

- `SPECTRA_INSPECTOR_APP_NAME`='Spectra Inspector' display name used by the app
- `SPECTRA_INSPECTOR_WRITE_DIR`='/path/to/a/writeable/directory' occasionally
  cleared by the frontend, used for storing temp files provided as downloads to
  user
- `SPECTRA_INSPECTOR_MAX_TMP_DIRS`=100 max number of tmp directories before they
  start clearing
- `SPECTRA_INSPECTOR_SERVER_HOST`=host to use. Use "host.docker.internal" for
  deployment when the `spectra_inspector_server` is running via docker on the
  same machine.
- `SPECTRA_INSPECTOR_SERVER_PORT`=port to access `spectra_inspector_server` api
  on

Unknown keys in `.env` are rejected rather than ignored, so a stale `.env` fails
fast: keys under the prefix that don't match a setting raise `extra_forbidden`,
and the pre-prefix spellings (`WRITE_DIR`, `SERVER_HOST`, ...) raise an error
listing their new names.

## Credits

Initial multi-page dash template modified from
https://github.com/open-resources/dash_curriculum

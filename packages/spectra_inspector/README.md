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
  user. In docker the compose files point this at a directory inside the
  container instead.
- `SPECTRA_INSPECTOR_MAX_TMP_DIRS`=100 max number of tmp directories before they
  start clearing
- `SPECTRA_INSPECTOR_EXPORT_SCALE_FACTORS`='2,1' the image sizes offered for the
  `.zip` summary export, as whole factors the map is reduced by (`1` writes
  every map pixel, `2` half the width and height). The first entry is the one
  preselected, so lead with a larger factor where downloads are slow. The PDF
  and `.pptx` always size their images to the page
- `SPECTRA_INSPECTOR_SERVER_HOST`=host to use. Only read when running outside
  docker: the compose files set it to the backend's service name (`fastapi`),
  which resolves over the compose network, so the backend needs no host port.
- `SPECTRA_INSPECTOR_SERVER_PORT`=port to access `spectra_inspector_server` api
  on. Likewise fixed to `8000` by the compose files.
- `SPECTRA_INSPECTOR_DESKTOP_MODE`=false. Set to `true` to show the
  working-directory picker on the data selection and inspector pages: it browses
  the server's data root and loads the datasets of the directory you pick into
  the sample dropdown. Requires `SPECTRA_INSPECTOR_DESKTOP_MODE=true` in the
  `spectra_inspector_server` `.env` as well — the endpoints it calls return
  `403` otherwise.
- `SPECTRA_INSPECTOR_INACTIVITY_TIMEOUT_SECONDS`=1800. Desktop mode only: after
  this long without mouse or keyboard input an overlay asks whether to continue
  or start a new session (which reloads the start page and drops the selected
  dataset, working directory and panels). `0` turns it off.
- `SPECTRA_INSPECTOR_N_FRONTEND_WORKERS`=2 gunicorn worker processes started by
  the docker image (`gunicorn spectra_inspector.main:server`). Not read by
  `serve.py`, which runs the flask development server.

Unknown keys in `.env` are rejected rather than ignored, so a stale `.env` fails
fast: keys under the prefix that don't match a setting raise `extra_forbidden`,
and the pre-prefix spellings (`WRITE_DIR`, `SERVER_HOST`, ...) raise an error
listing their new names.

## Credits

Initial multi-page dash template modified from
https://github.com/open-resources/dash_curriculum

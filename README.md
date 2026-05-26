# spectra_inspector

A dash-plotly web app for subsampling EDAX filesets

# Developer notes

## Deployment - Docker

### environment variables

Set in `.env`:

- `WRITE_DIR`='/path/to/a/writeable/directory' occasionally cleared by the
  frontend, used for storing temp files provided as downloads to user
- `MAX_TMP_DIRS`=100 max number of tmp directories before they start clearing
- `SERVER_HOST`=host to use. Use "host.docker.internal" for deployment when the
  `spectra_inspector_server` is running via docker on the same machine.
- `SERVER_PORT`=port to access `spectra_inspector_server` api on

## Credits

Initial multi-page dash template modified from
https://github.com/open-resources/dash_curriculum

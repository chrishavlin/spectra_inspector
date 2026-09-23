# CLAUDE.md — spectra_inspector_server

Backend-specific guidance for Claude Code. The root `CLAUDE.md` covers the
repository layout, commands, configuration, conventions, and commit rules; this
file is loaded only when working on files under this package.

Each module's docstring explains its own design (`processor/_polygon.py`,
`processor/_reductions.py`, `calibration.py`, `processor/file_loaders.py`, ...);
read it before changing the module. This file keeps the cross-module picture.

## Backend architecture

Data source is a filesystem scan, not a real database:

- `settings.py` → `dependencies.py` (`get_settings`, `get_database_session`,
  both `@lru_cache`) → `EDAXPathHandler` (`_file_tree_handling.py`) →
  `OnDiskDatabase` (`_database/on_disk_db.py`).
- `OnDiskDatabase` recursively walks `SPECTRA_INSPECTOR_DATA_ROOT` for `.spd`
  files with sibling `.spc`/`.ipr` (required) plus optional `.bmp`/`.xml`, keyed
  by **file basename**; a duplicate basename anywhere in the tree is skipped
  with a warning, first one wins. It also registers **every** `.spc` in
  `available_spectra`, so a name can be both a map and a spectrum; the
  per-sample endpoints take `spectrum_only: bool` to say which is meant.
  Rescanning only happens via `/available-datasets?refresh_db=true` and only
  when `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH=true`.
- `SPECTRA_INSPECTOR_DESKTOP_MODE=true` skips the startup walk and enables
  `/browse-directory` + `/datasets-in-directory` (403 otherwise). Every client
  path goes through `_file_browser.resolve_within_root`, which is the only thing
  confining browsing to the data root — new endpoints taking a path must use it.
- An optional `sample_metadata.csv` at the data root supplies lat/lon/group
  metadata for the frontend's sample map.
- `processor/file_loaders.py` loads metadata lazily through
  `rsciio.edax.file_reader`, then mmaps the `.spd` payload directly
  (`np.memmap`, deliberately bypassing rsciio's dask wrapper). Array axis order
  is `(index0, index1, channel)`; a spectrum-only dataset is 1D with the energy
  axis as its only axis.

Request flow for anything expensive: the `lifespan` context creates an
`asyncio.Queue` and a long-running `process_requests` consumer that dispatches
each item into a `ProcessPoolExecutor`. Endpoints build a `queueOpsItem`
(`ops_func` is the **string name of a method on `OperationEDAXStateHandler`**,
dispatched via `getattr`), push it with `submit_op`, then wait in
`await_op_result` on the `asyncio.Event` registered for that `ops_id` (2-minute
timeout → HTTP 404). `/info`, `/available-datasets`, and the metadata endpoints
skip the queue and run inline.

The pool holds a single worker and outlives the requests it serves, because
`load_edax_spd` caches the filesets it has opened (bounded, invalidated on
mtime/size) and re-mapping a cube costs tens of milliseconds of page faults even
when the file is still in the page cache. Anything that makes the worker
short-lived again gives that cost back.

So adding a heavy endpoint means: add a method to
`processor/operations.py::OperationEDAXStateHandler`, add response models to
`model.py`, enqueue a `queueOpsItem` naming that method, regenerate the frontend
models (see the root `CLAUDE.md`), and mirror the client call in the frontend's
`utilities/interface.py`. Large reductions chunk over axis 0
(`_DEFAULT_CHUNKSIZE`) and pick their accumulator through
`processor/_reductions.py::accumulator_dtype`; they are deliberately
single-threaded.

Request validation that needs no data load (index ranges against the header's
axis sizes, the `polygon` query parameter) happens in `main.py` and answers 422
before anything is queued. The `polygon` parameter is parsed by hand there
rather than through a pydantic model so the frontend's generated `model.py` is
unaffected. The server never clips a selection: the frontend clips boxes to the
image before asking, and a polygon is intersected with the map by
`processor/_polygon.py`.

Images cross the wire as `raveledImage` (flat list + shape), reshaped
client-side.

### Testing without EDAX data

`_testing.py` exposes `onDiscMock` with synthetic sample names
(`faked-dataset-C12`, `faked-dataset-2`, and `faked-spectrum-only` for a
spectrum with no map behind it) and `createEDAXMock()` /
`createEDAXSpectrumMock()`, which build full `EDAX_raw_ds` objects with
realistic headers. `pytest_running()` sniffs `PYTEST_VERSION`;
`main._valid_sample_name` and `OperationEDAXStateHandler._require_sample` accept
mock names only when it is true, so `TestClient` tests hit every endpoint
without a data root. Keep new endpoints going through those two guards or they
will be untestable. `write_mock_spc(path)` writes a genuine `.spc` so the real
loader can be exercised on a `tmp_path`.

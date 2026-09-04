# CLAUDE.md — spectra_inspector_server

Backend-specific guidance for Claude Code. The root `CLAUDE.md` covers the
repository layout, commands, configuration, conventions, and commit rules; this
file is loaded only when working on files under this package.

## Backend architecture

Data source is a filesystem scan, not a real database:

- `settings.py` → `dependencies.py` (`get_settings`, `get_database_session`,
  both `@lru_cache`) → `EDAXPathHandler` (`_file_tree_handling.py`) →
  `OnDiskDatabase` (`_database/on_disk_db.py`).
- `OnDiskDatabase` recursively walks `SPECTRA_INSPECTOR_DATA_ROOT` for `.spd`
  files that have sibling `.spc`/`.ipr` (required) plus optional `.bmp`/`.xml`,
  keyed by **file basename**; a basename seen a second time anywhere in the tree
  is skipped with a warning (`OnDiskDatabase.add_fileset` returns False), so the
  first one found wins rather than the scan erroring out. Rescanning only
  happens via `/available-datasets?refresh_db=true` and only when
  `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH=true`.
- `SPECTRA_INSPECTOR_DESKTOP_MODE=true` skips that startup walk entirely
  (`dependencies.get_database_session` passes `init_db=False`) and enables
  `/browse-directory` + `/datasets-in-directory`, which let a client walk the
  tree and scan one directory into the database
  (`OnDiskDatabase.set_working_directory`, replacing the previous contents).
  Every client path goes through `_file_browser.resolve_within_root`, which is
  the only thing confining browsing to the data root — new endpoints taking a
  path must use it. Both endpoints 403 when desktop mode is off.
- An optional `sample_metadata.csv` at the data root supplies lat/lon/group
  metadata used by the frontend's sample map. `_map_to_sample_name` derives a
  sample id from a map name by splitting on `"Map"`.
- `processor/file_loaders.py` loads metadata lazily through
  `rsciio.edax.file_reader`, then mmaps the `.spd` payload directly
  (`np.memmap`, deliberately bypassing rsciio's dask wrapper). Array axis order
  is `(index0, index1, channel)`.

Request flow for anything expensive: the `lifespan` context creates an
`asyncio.Queue` and a long-running `process_requests` consumer that dispatches
each item into a `ProcessPoolExecutor`. Endpoints build a `queueOpsItem`
(`ops_func` is the **string name of a method on `OperationEDAXStateHandler`**,
dispatched via `getattr`), push it with `submit_op`, then wait in
`await_op_result` on the `asyncio.Event` `submit_op` registered for that
`ops_id` (2-minute timeout → HTTP 404). `/info`, `/available-datasets`, and the
metadata endpoints skip the queue and run inline.

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
(`_DEFAULT_CHUNKSIZE = 128`) to avoid materializing the full cube, and go
through `processor/_reductions.py::accumulator_dtype` for what dominates them:
the narrowest accumulator that provably cannot overflow, because numpy's 32 bit
reduce loop runs about twice as fast as the 64 bit one. The reductions are
deliberately single-threaded.

Images cross the wire as `raveledImage` (flat list + shape), reshaped
client-side.

`calibration.py` computes per-element peak weights over fixed keV windows plus
the `DH_assessment` ratio; `Spectrum1d.get_weights()` attaches them to
`/image-spectrum` responses when `include_weights=true`.

### Testing without EDAX data

`_testing.py` exposes `onDiscMock` with two synthetic sample names
(`faked-dataset-C12`, `faked-dataset-2`) and `createEDAXMock()`, which builds a
full `EDAX_raw_ds` including realistic `original_metadata` headers.
`pytest_running()` sniffs `PYTEST_VERSION`; `main._valid_sample_name` and
`OperationEDAXStateHandler._require_sample` accept mock names only when it is
true, so `TestClient` tests hit every endpoint without a data root. Keep new
endpoints going through those two guards or they will be untestable.

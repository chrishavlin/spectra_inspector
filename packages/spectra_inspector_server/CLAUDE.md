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

### Spectrum-only datasets (issue #115)

Besides maps, the scan registers **every** `.spc` it sees in
`OnDiskDatabase.available_spectra` (`_recursive_inspection` / `find_spc_files`),
whether the file is standalone or the sidecar of a full set.
`AvailableDatasets.available_spectra` lists them next to `available_files`, and
`directoryListing.spectrum_count` counts them per directory. The two name spaces
overlap (`C-12` is both a map and its spectrum), so the per-sample endpoints
(`/image-metadata`, `/image-metadata-combined`, `/image-spectrum`) take
`spectrum_only: bool` to say which is meant; the image endpoints only ever serve
maps. With `spectrum_only`, `EDAXPathHandler.load_edax` goes through
`file_loaders.load_edax_spc`, which reads the lone `.spc` via rsciio into an
`EDAX_raw_ds` whose `data` is 1D and whose only axis is the energy axis, so
`CombinedMetadata.data_shape` is `(channel,)` and `axes_by_index` has key 0
only. `get_spectrum(..., spectrum_only=True)` returns the stored counts (index
ranges are ignored) and the weights / DH assessment come out as for a map.

### Testing without EDAX data

`_testing.py` exposes `onDiscMock` with two synthetic sample names
(`faked-dataset-C12`, `faked-dataset-2`) and `createEDAXMock()`, which builds a
full `EDAX_raw_ds` including realistic `original_metadata` headers.
`pytest_running()` sniffs `PYTEST_VERSION`; `main._valid_sample_name` and
`OperationEDAXStateHandler._require_sample` accept mock names only when it is
true, so `TestClient` tests hit every endpoint without a data root. Keep new
endpoints going through those two guards or they will be untestable.

For spectra, `onDiscMock.is_mock(name, spectrum_only=...)` accepts the map names
in both modes plus `faked-spectrum-only` as a spectrum with no map behind it
(`createEDAXSpectrumMock()`, 4096 channels of 10 eV so the calibration windows
are covered). `write_mock_spc(path)` writes a **genuine** `.spc` using rsciio's
own header dtype, so the real loader can be exercised on a `tmp_path` without
checking EDAX data into the repo (`tests/test_spectrum_only.py`).

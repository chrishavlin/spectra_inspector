# AGENTS.md — spectra_inspector_server

Backend-specific guidance; the root `AGENTS.md` covers the rest. Designs are
documented in docstrings next to the code — read them before changing a module.
This file keeps the cross-module rules.

## Rules

- **Paths from a client** go through `_file_browser.resolve_within_root`, the
  only thing confining browsing to the data root.
- **Anything that enumerates the tree** must honour
  `OnDiskDatabase.scan_exclusions` (`_database/scan_exclude.py`).
- **Per-sample endpoints** take `spectrum_only: bool`, because one name can be
  both a map and a spectrum (see `OnDiskDatabase`), and must check the name
  through `main._valid_sample_name` /
  `OperationEDAXStateHandler._require_sample` or they will be untestable without
  EDAX data (`_testing.py`).
- **The server never clips a selection**: validation that needs no data load
  answers 422 in `main.py` before anything is queued. The frontend clips boxes;
  polygons are intersected with the map by `processor/_polygon.py`.
- **Rescanning** happens only via `/available-datasets?refresh_db=true` and only
  in desktop mode.
- `precompute_derived_data.py --overwrite` empties the whole derived-data
  directory, spectral pyramids included.

## Adding a heavy endpoint

Anything expensive runs through the queue in `main.py` (`submit_op` /
`await_op_result`) into a single long-lived worker process; `/info`,
`/available-datasets` and the metadata endpoints run inline.

1. Add a method to `processor/operations.py::OperationEDAXStateHandler`.
2. Add response models to `model.py`.
3. Enqueue a `queueOpsItem` whose `ops_func` is that method's name.
4. Regenerate the frontend models (root `AGENTS.md`).
5. Mirror the client call in the frontend's `utilities/interface.py`.

Large reductions chunk over axis 0 and pick their accumulator through
`processor/_reductions.py::accumulator_dtype`; they are deliberately
single-threaded.

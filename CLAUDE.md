# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Repository layout

Two **independent** uv projects under `packages/`. There is no root
`pyproject.toml` and no uv workspace — every `uv` command must be run from
inside one of the package directories (the README's "run `uv sync` from the
repository root" is stale).

- `packages/spectra_inspector_server/` — FastAPI backend (Python >=3.12) that
  reads EDAX filesets off a local filesystem.
- `packages/spectra_inspector/` — Dash/Plotly frontend (Python >=3.13) that
  talks to the backend over HTTP only.

The frontend does **not** depend on the server package. It re-declares the
server's pydantic/dataclass response models in
`spectra_inspector/utilities/model.py`. **Changing a response model on the
server requires the matching edit in the frontend copy** — nothing enforces
this, and drift already exists (e.g. `EDAX_file_set` optional fields,
`sampleMetadataCSVrecord` nullability).

## Commands

Run from the relevant package directory.

```sh
# tests (CI runs exactly this)
uv run --group test pytest src
uv run --group test pytest src/spectra_inspector_server/tests/test_calibration.py::test_sum_in_range_with_shift  # single test

# type checking — server only, strict mypy (CI); the server README's `ty check` is stale
cd packages/spectra_inspector_server && uv sync --group typing && uv run mypy src/*

# lint/format — pre-commit (ruff check+format, prettier, etc.), run from repo root
uv run pre-commit run --all-files

# lockfiles must stay in sync (CI check)
uv lock --check
```

Running the app locally (two terminals):

```sh
cd packages/spectra_inspector_server && uv run fastapi run src/spectra_inspector_server/main.py  # :8000, /docs
cd packages/spectra_inspector           && uv run python serve.py                                # :8050
```

Docker: `./start_docker.sh` (or `.ps1`/`.bat`) wraps `docker compose` and passes
both packages' `.env` files.

Note: `[tool.pytest]` in the server's `pyproject.toml` is not a table pytest
reads (`[tool.pytest.ini_options]` is), so `testpaths`/`filterwarnings` there
have no effect — always pass `src` explicitly.

### Configuration gotcha

Each package reads its own `.env` (pydantic-settings, `env_file=".env"`,
untracked; templates are `defaults.env`). Settings models forbid extra keys, so
a `.env` containing names that don't match the model's fields raises
`extra_forbidden` and **fails tests and app startup**. In particular the
frontend's fields are unprefixed (`APP_NAME`, `WRITE_DIR`, `MAX_TMP_DIRS`,
`SERVER_HOST`, `SERVER_PORT`) while the server's are mostly
`SPECTRA_INSPECTOR_*`-prefixed. If frontend tests fail with pydantic validation
errors, check `packages/spectra_inspector/.env` against
`spectra_inspector/settings.py` — CI passes because no `.env` exists there.

## Backend architecture

Data source is a filesystem scan, not a real database:

- `settings.py` → `dependencies.py` (`get_settings`, `get_database_session`,
  both `@lru_cache`) → `EDAXPathHandler` (`_file_tree_handling.py`) →
  `OnDiskDatabase` (`_database/on_disk_db.py`).
- `OnDiskDatabase` recursively walks `SPECTRA_INSPECTOR_DATA_ROOT` for `.spd`
  files that have sibling `.spc`/`.ipr` (required) plus optional `.bmp`/`.xml`,
  keyed by **file basename, which must be globally unique** across the tree.
  Rescanning only happens via `/available-datasets?refresh_db=true` and only
  when `SPECTRA_INSPECTOR_ALLOW_DB_REFRESH=true`.
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
dispatched via `getattr`), push it, then poll the module-level `_results` dict
by `ops_id` in `await_op_result` (2-minute timeout → HTTP 404). `/info`,
`/available-datasets`, and the metadata endpoints skip the queue and run inline.

So adding a heavy endpoint means: add a method to
`processor/operations.py::OperationEDAXStateHandler`, add response models to
`model.py`, enqueue a `queueOpsItem` naming that method, and mirror the client
call in the frontend's `utilities/interface.py`. Large reductions chunk over
axis 0 (`_DEFAULT_CHUNKSIZE = 128`) to avoid materializing the full cube.

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

## Frontend architecture

Dash multi-page app: `main.py` builds `Dash(use_pages=True)` with a fixed
sidebar and theme switcher; `pages/*.py` self-register via `dash.register_page`.
`pages/data_selection.py` is `/` (sample picker + map), `pages/inspector.py` is
`/inspector/<sample_name>` and holds ~all the callback logic. `serve.py` is the
entry point (`--debug/--host/--port`).

All cross-callback state lives in a single `dcc.Store` with id
`USER_STORE_DIV_ID` (`"user-mem-store"`), whose dict is the `UserStore`
dataclass (`user_store_model.py`). Read it as `UserStore(**store_dict)`, write
it with `updateDataStore(store_dict, key, value)`. Selected-sample metadata is
carried as a JSON string (`metadata_json`) and lazily refetched by
`conditionally_fetch_metadata()`. `pages/inspector.py` adds several page-local
stores (`graph-id-store`, `processed-graph-ids`, `active-shapes`,
`full-spectrum-store`, `active-spectrum-metadata`) tracked in `inspectorIDs`.

**Component id convention** — every reusable component defines a subclass of
`indexedLayoutIDMapper` (`components/layout_ids.py`) that declares `prop_names`
and one `@property` per element returning `self.full_id("-suffix")`. Use
`ids.get_id_with_index(prop)` to emit a pattern-matching id
(`{"type": ..., "index": ...}`) for dynamically added components — the inspector
page relies on `ALL`/`MATCH` over these to support an arbitrary number of image
panels. Component tests assert the `prop_names` round-trip
(`test_bitmap_image.py`), so add new props to `prop_names`.

Backend access goes exclusively through
`utilities/interface.py::SpectraInspectorServerInterface`, which builds its URI
from `Settings` and exposes `.connected` for graceful degradation (layouts
render a "could not connect" div rather than raising). Frontend tests mock
`requests.get` via `pytest-mock`.

Other things worth knowing:

- Sample names may contain spaces but appear in URL paths, so
  `utilities/coerce.py` swaps them with the `___` placeholder
  (`spaces_to_placeholder` / `placeholder_to_spaces`).
- Figures are Plotly `px.imshow` with `dragmode="drawrect"`; user rectangles
  come back through `relayoutData` and become index ranges sent to the backend.
- Export: `utilities/summary_writer.py` writes into a uuid subdirectory under
  `WRITE_DIR` and prunes oldest dirs past `MAX_TMP_DIRS`; `plotly_to_matplotlib`
  in `coerce.py` re-renders figures for PDF output, and `utilities/msa_io.py`
  handles EMSA `.msa`/`.csv` round-tripping.
- `utilities/element_energy_ranges.py` (3 elements, drives the slider presets)
  is separate from and narrower than the server's
  `calibration.element_energy_ranges_keV` (9 elements).

## Conventions

- Ruff with a broad rule set in both packages (`T20` bans `print` outside tests,
  `EM` requires exception messages be bound to a variable first, `PTH` prefers
  pathlib). Log through the shared `spectraLogger` (`spectra_inspector.logging`
  / `spectra_inspector_server._logging`).
- Server code is strict-mypy and fully annotated (`disallow_untyped_defs` for
  `spectra_inspector_server.*`); frontend code is not type-checked in CI and
  Dash callbacks are commonly left unannotated.
- Class naming is inconsistent by design in the frontend: layout-id and model
  helper classes use lowerCamelCase (`bitmapImageLayoutIDs`, `raveledImage`).
  Match the surrounding file.
- Test files must be named `test_*.py` (pre-commit
  `name-tests-test --pytest-test-first`). A local `disallow-caps` pygrep hook
  rejects mis-capitalized project names anywhere in the repo (numpy, pytest,
  GitHub, CMake, pybind11, ccache) — see the pattern in
  `.pre-commit-config.yaml` for the exact spellings it bans.

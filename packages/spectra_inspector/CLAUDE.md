# CLAUDE.md — spectra_inspector

Frontend-specific guidance for Claude Code. The root `CLAUDE.md` covers the
repository layout, commands, configuration, conventions, and commit rules; this
file is loaded only when working on files under this package.

## Frontend architecture

Dash multi-page app: `main.py` builds `Dash(use_pages=True)` with a fixed
sidebar and theme switcher; `pages/*.py` self-register via `dash.register_page`.
`pages/data_selection.py` is `/` (sample picker + map), `pages/inspector.py` is
`/inspector/<sample_name>` and holds ~all the callback logic. `serve.py` is the
entry point (`--debug/--host/--port`).

`components/directory_selector.py` is the desktop-mode working-directory picker,
embedded in both pages (index 0 on data selection, index 1 on the inspector) and
rendered as an empty div unless `Settings().desktop_mode`. Its callbacks are
`MATCH`-keyed on that index, which is how "Use this directory" can write the
options of the `datasetSelectorLayoutIDs` dropdown sharing the same index. Both
packages carry their own `desktop_mode` setting and both must be enabled.

Two Dash rules bit this component, and neither is enforced in python -- the app
starts, `/_dash-update-component` answers hand-made requests, and the failure
only appears once a browser wires the page up:

- every `Output` of a callback must carry `MATCH` on the same keys, so a plain
  id (`user-mem-store`) cannot share a callback with `MATCH` outputs. That is
  why committing a directory writes a page-local store and a second callback
  (`ALL` input, plain output) copies it into the user store.
  `tests/test_callback_wildcards.py` mirrors the rule over `app._callback_list`.
- a prop cannot be both written and read back around a loop. Subdirectories are
  clickable `ListGroupItem`s rather than a dropdown for this reason: clearing a
  dropdown value from the callback that renders the listing is a cycle.

Verify changes here in an actual browser, not just via callback invocation.

### Browser testing without EDAX data

The inspector's image panels are independent `dcc.Graph`s kept in step by
callbacks, and whether they actually stay in step (zoom, tool, box) only shows
in a browser. A headless setup that needs no data:

- Backend: `PYTEST_VERSION=1 SPECTRA_INSPECTOR_DATA_ROOT=<any empty dir>` makes
  `faked-dataset-C12` a valid sample everywhere (`pytest_running()`), but
  `/available-datasets` will not list it, and the inspector's dataset dropdown
  clears a value that is not among its options, so the page renders nothing. Run
  the server through a small wrapper that patches
  `main._available_datasets_response` to append `onDiscMock.filenames`; the same
  wrapper can patch `_testing.createEDAXMock` to a 512x512 shape so callback
  timings resemble real maps (the default mock is 16x16).
- Frontend: `uv run python serve.py --port 8050`, then open
  `/inspector/faked-dataset-C12`.
- Driver: playwright in a throwaway venv with
  `p.chromium.launch(channel="chrome")` uses the installed Google Chrome, no
  browser download. Read a panel's state from
  `document.querySelectorAll('.js-plotly-plot')[i]._fullLayout` (ranges,
  dragmode, shapes), click tools via `.modebar-btn[data-title="Zoom"]`, and drag
  on the panel's `.nsewdrag` rect. Compare `_fullLayout` across panels rather
  than the Dash `figure` prop.
- While a `dcc.Loading` overlay is showing, the panel swallows mouse events:
  wait for `.dash-spinner` to disappear before dragging.

### Syncing the image panels (issue #65)

Several Dash/plotly behaviours here are not visible from the python side:

- The graph `figure` prop never receives plotly's zoom ranges, so a callback
  cannot read the current view off `State(graph, "figure")`. The view is rebuilt
  from `relayoutData` keys (`"xaxis.range[0]"`, `"xaxis.autorange"`,
  `"shapes[0].x1"`, ...) in `utilities/view_sync.py` and kept in the
  `image-view-store`; `sync_image_views` applies it to every panel as a `Patch`,
  so no image data crosses the wire. Keep relayout events out of
  `update_graph_figure`: every `State` is uploaded with the request, and that
  callback reads the full figures.
- px.imshow sets `constrain="domain"`; plotly.js resolves that against a private
  record of the last interactively set range, so a range set from python comes
  out a few pixels different from the same zoom dragged in the browser.
  `get_new_im` sets `constrain="range"` on both axes, which depends only on the
  current range and lands every panel on the same view.
- Removing a panel fires callbacks with wildcard inputs and reports _every_
  remaining panel's input props as triggered (`ctx.triggered_prop_ids` has
  several entries); a real click or dropdown pick reports one.
- The per-panel `dcc.Loading` uses `delay_show` so quick layout patches never
  raise its overlay, which blocks the mouse while visible.
- Dash fires a callback only when a prop's value actually changes, and plotly
  reports every double click as the same `{"xaxis.autorange": true, ...}` (a
  re-picked tool likewise). `sync_image_views` therefore clears the triggering
  graph's `relayoutData` with `dash.set_props` once it has read it; a side
  update like that does not re-trigger callbacks, so it costs nothing.

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
  `SPECTRA_INSPECTOR_WRITE_DIR` and prunes oldest dirs past
  `SPECTRA_INSPECTOR_MAX_TMP_DIRS`; `plotly_to_matplotlib` in `coerce.py`
  re-renders figures for PDF output, and `utilities/msa_io.py` handles EMSA
  `.msa`/`.csv` round-tripping.
- `utilities/element_energy_ranges.py` (3 elements, drives the slider presets)
  is separate from and narrower than the server's
  `calibration.element_energy_ranges_keV` (9 elements).

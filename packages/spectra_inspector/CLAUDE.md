# CLAUDE.md — spectra_inspector

Frontend-specific guidance for Claude Code. The root `CLAUDE.md` covers the
repository layout, commands, configuration, conventions, and commit rules; this
file is loaded only when working on files under this package.

## Frontend architecture

Dash multi-page app: `main.py` builds `Dash(use_pages=True)` with a fixed
sidebar and theme switcher; `pages/*.py` self-register via `dash.register_page`.
Page-chrome styling lives in `assets/layout.css` (served by Dash automatically
from the directory next to `main.py`): the sidebar width is a CSS variable that
steps from 16rem to 12rem below `xl`, and below `md` the sidebar is hidden in
favour of a top bar with a hamburger that opens a `dbc.Offcanvas` copy of the
nav (issue #124). Use Bootstrap's `--bs-*` variables rather than literal colours
there so the `ThemeSwitchAIO` stylesheet swap keeps working.
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

`components/dataset_selector.py` carries the **"Spectrum only" switch** (issue
#115). The server always sends both name lists; the switch picks which one the
dropdown shows (never both -- a standalone `.spc` is not offered as a map), and
a page-local `liststore` keeps both lists so a flip needs no round trip. The
mode itself lives in the user store (`spectrum_only`) and rides along on every
per-sample request. Things that only show in the browser:

- Pages are rebuilt on navigation and the layout cannot read the user store, so
  the inspector gets the mode from the `?spectrum_only=true` query string the
  "Load Selected" link carries; `hydrate_spectrum_only` then sets the switch
  from the store on mount, and `toggle_spectrum_only` (an `ALL` callback, so it
  can also write the plain-id user store) tells a hydration apart from a user
  flip by comparing the switch to the store. A flip clears the selection, since
  the same name means the other kind of dataset. `resolve_spectrum_only` falls
  back to the switch while the store has no mode yet (fresh session on a URL).
- Callbacks whose outputs already exist in the app layout (the user store)
  **do** fire when only their inputs are inserted with a page, despite
  `prevent_initial_call=True`; that is how every page's
  `update_selected_dataset` runs on load, and it is chained after the toggle
  callback because the dropdown value is an input of it.
- Dropdown option labels must stay **plain strings**. A component label is
  mounted by dash-renderer with a path into the layout tree; after a callback
  replaces the options that path is stale, and reopening the menu crashed the
  renderer, which re-mounted the page from the stale layout and flipped the
  switch back. The dark theme's white-on-white value text is fixed with a
  `color` on the dropdown's `style` instead.
- In spectrum-only mode the inspector hides the image buttons and the panel area
  (`inspectorIDs.image_controls` / `image_section`) and `initial_update` opens
  no panels; only the spectrum and the export panel remain. `export_summary`
  resolves the mode the same way and, when it is on, never looks at the image
  panels or the box store: the zip / PDF carry the spectrum files only
  (`tests/test_export_summary.py`).

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
  `.msa`/`.csv` round-tripping. Every export also carries a metadata record
  (issue #42) built by `utilities/export_metadata.build_export_metadata`: the
  zip gets it as `metadata.json` plus a `README.txt` listing the files, the PDF
  renders it as text pages. Its `sample` part is `sample_metadata_display_dict`,
  the same dict the data-selection page's accordion shows (the combined metadata
  dump plus the sample sheet record), so change one and the other follows;
  `subselection` gives the box as half-open index ranges and as bounds in each
  axis's own units (index 0 is the image rows). The record is built in the
  export callback from `conditionally_fetch_metadata()`, and a fetch failure
  leaves `sample` null rather than losing the export. Core PDF fonts are
  latin-1, so `_pdf_safe` replaces what they cannot encode.
- The element presets of the energy-range slider are the server's calibration
  windows (issue #116). The server keeps them as the _defaults_ of
  `calibration.ElementEnergyRanges`, which rides on the `/info` response so the
  model (defaults included) lands in the generated `utilities/model.py`;
  `utilities/element_energy_ranges.get_element_energy_ranges` reads
  `ElementEnergyRanges()` from there, no request involved. Changing a window on
  the server therefore needs the codegen step. The inspector names the presets
  its first three panels open on (`_INITIAL_PANEL_ELEMENTS`) rather than
  indexing into the server order.
- Peak integration windows (issues #44, #120): the spectrum response carries
  `integration_ranges_keV` next to `weights` (both absent when the server cannot
  calibrate), stored in the spectrum's `attrs` like the weights.
  `utilities/peak_windows.py` turns each visible window into a `fill="toself"`
  scatter trace between the curve and a per-window baseline (the mean of the
  first and last sample inside the window), tagged with `meta.peak_window` so
  `apply_peak_windows` can strip and rebuild them, plus paper-anchored layout
  `shapes` (a dotted centre line) and `annotations` (the element label on that
  line, staggered over two rows when neighbours crowd). A peak is drawn only
  while its element's weight is above zero after the zeroed-out elements are
  applied, so `visible_elements` hides what the DH assessment found nothing for
  and what the user has zeroed (reset restores it). The "peak windows" switch
  and the `zeroed-elements` store both feed `toggle_peak_windows`, which returns
  the whole figure (the fills live in `data`, out of `Patch`'s reach), and are
  `State`s of `update_spectrum` and `export_summary`; the export rebuilds the
  peaks from those rather than trusting the figure prop, and
  `plotly_to_matplotlib` draws `toself` traces with `ax.fill` and the
  paper-spanning shapes with `axvline`. Plotly shows a legend as soon as a
  second trace exists, so the layout pins `showlegend=False`. The weights
  table's swatches come from the same `spectrum_element_colors` (assigned in the
  server's calibration order, so hiding a peak never shifts a colour) and are
  muted for a peak not drawn.

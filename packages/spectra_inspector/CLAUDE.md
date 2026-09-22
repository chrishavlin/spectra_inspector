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

Layout widths are container-driven rather than viewport-driven: Bootstrap's
`xs`/`lg` breakpoints key on the window, so with the sidebar taking a fixed
slice a 1366px laptop is still `xl` and a fixed `dbc.Col(width=4)` gave three
panels too narrow to read. The inspector's `image_container` is therefore a
plain `html.Div` styled as a CSS grid (`repeat(auto-fill, minmax(420px, 1fr))`)
and `add_or_delete_image` appends each panel card directly, no `Col` wrapper;
the deletion path pops children by index so it does not care. Elsewhere prefer
`width="auto"` columns next to one flexing column over fixed integer widths and
empty spacer columns. Inside a panel the element dropdown, `Apply` and the
delete `X` live in the `CardHeader`, and `energy_range_slider` exposes those
pieces through `build_element_dropdown_and_slider` (an
`elementDropdownSliderParts`); `get_element_dropdown_and_slider` still returns
the one-block version for anything that wants it.

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
- In spectrum-only mode the inspector hides the image section, the toolbox and
  the panel area together (`inspectorIDs.image_section`), and `initial_update`
  opens no panels; only the spectrum and the export panel remain.
  `export_summary` resolves the mode the same way and, when it is on, never
  looks at the image panels or the box store: the zip / PDF carry the spectrum
  files only (`tests/test_export_summary.py`).

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
  dragmode, shapes), click tools in the toolbox card (the panels have no
  modebar) via their pattern ids,
  `[id='{"index":"zoom","type":"image-toolbox-tool"}']`, and drag on the panel's
  `.nsewdrag` rect. Compare `_fullLayout` across panels rather than the Dash
  `figure` prop.
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
- A colormap pick is answered by `recolor_image` alone. px.imshow keeps the
  scale on `layout.coloraxis.colorscale`, so `bitmap_image.colorscale_patch`
  sends the named scale's colour list as a layout `Patch` and the image data
  never leaves the browser. The dropdowns are `State`s of `update_graph_figure`
  (new and refreshed panels still need them), not inputs: every `State` is
  uploaded whichever input fired, and that callback reads the full figures.
- `add_or_delete_image` never declares the container's children as a `State`.
  dash-renderer serves `State`s from its layout store, so that value carries
  every panel's current figure, image included. Adding appends to a `Patch`,
  deleting `del`s by index on one, with the position taken from
  `graph-id-store`.
- Dash fires a callback only when a prop's value actually changes, and plotly
  reports every double click as the same `{"xaxis.autorange": true, ...}` (a
  re-picked tool likewise). `sync_image_views` therefore clears the triggering
  graph's `relayoutData` with `dash.set_props` once it has read it; a side
  update like that does not re-trigger callbacks, so it costs nothing.
- The panels' plotly modebars are off (`displayModeBar: False`); the tools live
  in `components/image_toolbox.py`, one card above the panels (inside
  `image_section`, so spectrum-only mode hides it too). A _tool_ is a plotly
  dragmode (`drawrect`, `zoom`, `pan`) or the polygon tool (below), and the
  **active tool is the view store's `dragmode`** -- there is no separate tool
  store: `select_image_tool` patches the tool's layout (`view_sync.tool_layout`:
  `dragmode` plus the axes' `fixedrange`) on every built panel and writes the
  view, `highlight_image_tool` sets the buttons' `active` from the view store
  (so a reset or a dataset switch, which empties the view, presses the default
  again), and new panels pick the tool up through `apply_view_to_figure`. An
  _action_ (`zoomin`, `zoomout`, `eraseshape`) is answered by `run_image_action`
  with layout patches only: a zoom step is `view_sync.zoom_view` about the
  centre (an un-zoomed axis spans the full image, whose shape comes from the
  metadata via `scaling.get_image_shape`), and erasing writes an empty
  `active-shapes` so the spectrum reloads. Buttons are pattern ids
  `{"type": "image-toolbox-tool"|"image-toolbox-action", "index": <id>}` over
  `ALL`; add a tool or action to the `toolboxSpec` in `image_toolbox.py`
  (`IMAGE_TOOLBOX`: the buttons plus the labelled rows they sit in, validated at
  import), and an action to `action_results`. `Add Image`, `Reset Extent` and
  `Submit shape` share the card but are plain ids (`ids.button_id("add")` /
  `("reset")` / `("submit")`) answered by `add_or_delete_image`,
  `update_graph_figure` and `submit_polygon`. The card's third row, Panel Mode,
  holds the single / multi-channel switch (`inspectorIDs.image_mode`), built by
  the page and passed into `image_toolbox_layout`. Plotly's per-panel PNG
  download went with the modebar; the export panel covers images.
- The **polygon tool** (`drawpolygon`, `view_sync.POLYGON_TOOL`) is not a plotly
  dragmode: its layout is `dragmode=False` with both axes `fixedrange`, which
  also disables plotly's double-click reset so a double click can remove a
  corner. Corners are placed by clicking a panel, moved by dragging, removed by
  a double click, and inserted by a double click on a segment. Plotly's own
  click event snaps to a pixel and reaches Dash as `clickData`, where two
  identical clicks in a row are deduplicated, so gestures never go through a
  callback input: document-level listeners in `assets/toolbox.js` (keyed on that
  layout signature) convert the pointer position with `xaxis.p2d`, wait
  `POLYGON_DBLCLICK_MS` for a second click at the same spot, and write
  `{kind: "click"|"dblclick"|"move", x, y, index, n}` into the `polygon-click`
  store with `dash_clientside.set_props`, which does fire dependent callbacks. A
  drag starts on a mousedown within `POLYGON_VERTEX_PX` of a corner (read off
  the named `polygon-vertex` circles in `gd.layout.shapes`); while the mouse is
  down the corner follows on every panel through `Plotly.react` with the same
  data and new shapes, and the release emits the `move`. It must be `react`, not
  `relayout`: `Plotly.relayout` emits `plotly_relayout`, which Dash turns into
  `relayoutData` and `sync_image_views` into a server round trip per frame (and
  into a one-shape store, since it keeps the last shape). Escape abandons a
  drag. `edit_polygon` answers every gesture with `layout.shapes` patches on
  every built panel and the shapes store; nearness for picking a corner or a
  segment is `pick_tolerance`, a fraction of the visible extent, and a single
  click that lands on a corner adds nothing. `utilities/selection.py` owns the
  store's shape: a box is the plotly rectangle in `active_shapes` as before; a
  polygon keeps its `points` (and the `submitted` copy, plus the marker radius)
  under `polygon`, with `active_shapes` drawn from the points (a `path`, closed
  from three points, and a `circle` per corner: green where the path starts, red
  where it ends, white in between, `vertex_color`). Only a submitted polygon or
  a box is the `selection_from_store`; `update_spectrum` compares the figure's
  `uirevision` (`_spectrum_revision`, built on `selection_key`) with the store's
  and returns `no_update` when the selection has not changed, which is what
  keeps corner edits from refetching until `Submit shape`. The controls
  (`polygon_controls`: the button and the how-to note) are shown by
  `toggle_polygon_controls` while the tool is pressed and the button enabled by
  `polygon_is_submittable`. Drawing a box replaces the polygon
  (`shapes_from_relayout` keeps the last shape), erase drops both. The corner
  markers are circles in data units, sized by `vertex_radius_for` from the
  visible extent: plotly's pixel-sized shapes (`xsizemode: "pixel"`) leak that
  mode into the subplot's `plotinfo`, and a box drawn afterwards comes out in
  pixels. The server sums the polygon (see
  `spectra_inspector_server/CLAUDE.md`); `polygonSelection.vertices` hands it
  `[index0, index1]` pairs. The export crops the `*_subset` images to the pixel
  rectangle around the polygon (`polygonSelection.bounding_box`: every pixel a
  corner lands in, wider than the centres-inside set the server sums) and
  records the corners in `subselection.polygon`. The exported images never copy
  the browser's shapes: `_image_figures_to_write` replaces them with
  `selection.overlay_shapes` (the box as the pixel-aligned rectangle of what was
  summed, the polygon as an unfilled outline plus a dot per corner, shifted to
  the crop's origin on the subset and left off a box's own crop) in the
  `outlineStyle` the export panel's **Figure export settings** give: a "draw the
  outline" checkbox and line / dot colour pickers (white by default), shown by
  `toggle_figure_export_settings` only while a selection exists. The pickers are
  `dbc.Input(type="color")`, the browser's native picker: `color` is not in the
  types dbc declares (its propTypes `oneOf` and the Python `Literal`), but the
  component passes the type through to the `<input>` and reads the value like
  any other, so it works and only a props-check in debug mode could object;
  `outline_style` accepts nothing but `#rrggbb` from it. `plotly_to_matplotlib`
  draws `rect`, `path` and `circle` shapes in their own colours (`mpl_color`
  turns `rgba(...)` into fractions).
- `components/toolbox.py` holds what the two toolboxes share: the button and row
  dataclasses, the view-control specs, the id mapper, the card builder
  (`toolbox_card`, whose `extras` slot ready-made components into a row) and the
  collapse wrapper. It is configuration, not a class hierarchy: the callbacks
  are each toolbox's own.
- The spectrum's modebar is off too. `components/spectrum_toolbox.py` folds
  "Spectrum Plot Tools" under the plot behind a `Plot tools` toggle (closed on
  load, flipped by the `toggleCollapse` clientside function in
  `assets/toolbox.js`), with the peak-windows switch and the y-scale radio in
  its Display row. Only the tool goes through the server: `select_spectrum_tool`
  patches `layout.dragmode` and writes the `spectrum-view` store,
  `highlight_spectrum_tool` reads it, and the callbacks that replace the
  spectrum figure (`update_spectrum`, `toggle_peak_windows`) put the stored
  dragmode on what they return so the pressed button survives a rebuild. The
  figure carries a `uirevision` (`_spectrum_revision`: the sample and the box)
  because the figure prop never receives the browser's zoom: without it a
  dragmode patch or a peak redraw snapped the plot back to autorange. A y-scale
  change bumps `yaxis.uirevision` so only that axis resets. Zoom in, zoom out
  and reset are the `spectrumAction` clientside function: the spectrum's live
  ranges exist only in the browser, so it reads `gd._fullLayout` and calls
  `Plotly.relayout`, scaling the energy axis only and reporting into the
  `spectrum-action-sink` store.

### Multi-channel (composite) panels

The image toolbox's Panel Mode row carries a two-way mode switch
(`inspectorIDs.image_mode`, `IMAGE_MODE_SINGLE` / `IMAGE_MODE_MULTI`). Flipping
it runs `switch_image_mode`, which replaces the container's children wholesale
(three element maps, or one composite), resets `graph-id-store` and empties
`processed-graph-ids`; the shared view and box are kept, so the new panels open
on the same zoom. `add_or_delete_image` reads the mode as a `State` and appends
a panel of the current kind; panel indices come from the store's `next_index`
rather than from the button's click count, so a panel never reuses the index of
one that was replaced.

`components/composite_image.py` builds the composite card. Its card, graph,
delete button and loading overlay carry the same `bitmap-image` ids as a single
panel, which is what makes `sync_image_views`, the box, the reset and the delete
path work on both kinds unchanged. Everything composite-specific has its own id
types: `composite-image-apply` / `-detailsbutton` / `-details` per panel, and
per channel (index `"<panel>-<channel>"`, see `channel_index`) a
`composite-channel-selector-*` element dropdown and energy slider (the shared
`energy_range_slider` pieces built under another `id_type_base`, with
`custom`/`off` entries instead of `none`; `register_element_selector_callbacks`
registers the dropdown/slider syncing per base), plus `composite-channel-badge`
/ `-color` / `-stretch`. The channel row always shows the numbered swatch and
element dropdown; colour, energy window and percentile stretch sit in the
details collapse. The swatch follows a colour pick at once, the image waits for
Apply.

Both kinds of Apply button say when they need pressing. A change to a panel's
controls turns the button `primary` and adds the `si-apply-pending` class (a
short pulse in `assets/layout.css`) from the browser, through the `applyButton`
clientside functions in `assets/apply_button.js`: `MATCH` for a single panel
(`register_apply_pending_callback` in `energy_range_slider.py`), `ALL` plus the
triggered id for a composite, whose controls are indexed per channel while Apply
is per panel. A user's change reaches a marker as the changed control alone or
batched with the slider move the element sync answers a dropdown pick with (one
or two props of one control index); a panel's insertion or removal never reaches
them (`prevent_initial_call` covers a new panel's own outputs, and a removal
re-fires neither, checked in the browser), and a call reporting several controls
marks nothing. `update_graph_figure` and `update_composite_figure` send
`APPLY_IDLE_PROPS` back with `set_props` for the panel they refreshed, and a
single panel seeded from another's figure is sent `APPLY_PENDING_PROPS`, since
its image is a copy of what its controls say. The extent reset leaves the marks
alone: it re-fetches nothing.

Two consequences for the page callbacks:

- `update_graph_figure` only builds panels that have a single-panel Apply button
  (it reads their ids), and `update_composite_figure` answers the composite
  Apply. Both write `processed-graph-ids` and can run at the same time (a mode
  switch removes one kind's inputs while inserting the other's), so each returns
  `no_update` for that store unless it actually added to it. The composite
  builder reads no figures: a composite always fetches its own channels
  (`fetch_im_data_parallel` over every new panel's active channels).
- The blend (`utilities/composite.py`) normalises each channel to its own
  percentile stretch, tints it a single hue from a fixed palette and sums; the
  figure is a `px.imshow` RGB image whose pixels travel as a base64 PNG in
  `data[0].source`. `recolor_image` never sees a composite (no colorscale
  dropdown), and `coerce.plotly_image_trace_to_array` decodes the PNG for the
  export, which names the files `bitmap_NN_composite_<elements>` and records one
  `channels` list per panel in the metadata. `export_summary` sorts panels into
  kinds by graph index (`_panel_exports`), so the single-panel lists are matched
  by slider id rather than by position when the ids are present.

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
- Figures are Plotly `px.imshow` with `dragmode="drawrect"` (the toolbox's
  default tool); user rectangles come back through `relayoutData` and become
  index ranges sent to the backend, a submitted polygon becomes the `polygon`
  query parameter (`utilities/selection.py`). The server answers an index range
  past the map with a 422 and never clips, so a box dragged out over the image's
  edge is stored and drawn as the user left it but clipped to the image when it
  becomes a request (`box_from_shape` with the image shape, via
  `_selection_for_request` for the spectrum and `selection_from_store` with the
  metadata's shape in the export). A box with no pixel inside the map is never a
  selection: `_shapes_after_relayout` puts the panels back to the stored shapes
  and leaves the store alone. A polygon needs none of this: it is sent as
  geometry and the server intersects it with the map itself.
- On a fresh load the figure callbacks can run before `update_selected_dataset`
  has written the user store, which then still names the `UserStore` default
  dataset `"none"`; `_ensure_dataset` puts the page's sample in for the
  callbacks that read the store (they fetch the metadata themselves then).
- Export: `utilities/summary_writer.py` writes into a uuid subdirectory under
  `SPECTRA_INSPECTOR_WRITE_DIR` and prunes oldest dirs past
  `SPECTRA_INSPECTOR_MAX_TMP_DIRS`; `plotly_to_matplotlib` in `coerce.py`
  re-renders figures for PDF output, and `utilities/msa_io.py` handles EMSA
  `.msa`/`.csv` round-tripping. Every export also carries a metadata record
  built by `utilities/export_metadata.build_export_metadata`: the zip gets it as
  `metadata.json` plus a `README.txt` listing the files, the PDF renders it as
  text pages. Its `sample` part is `sample_metadata_display_dict`, the same dict
  the data-selection page's accordion shows (the combined metadata dump plus the
  sample sheet record), so change one and the other follows; `subselection`
  gives the box as half-open index ranges and as bounds in each axis's own units
  (index 0 is the image rows). The record is built in the export callback from
  `conditionally_fetch_metadata()`, and a fetch failure leaves `sample` null
  rather than losing the export. Core PDF fonts are latin-1, so `_pdf_safe`
  replaces what they cannot encode.
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

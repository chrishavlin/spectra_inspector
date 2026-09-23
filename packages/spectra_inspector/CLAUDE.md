# CLAUDE.md — spectra_inspector

Frontend-specific guidance for Claude Code. The root `CLAUDE.md` covers the
repository layout, commands, configuration, conventions, and commit rules; this
file is loaded only when working on files under this package.

Each module under `components/` and `utilities/` opens with a docstring
explaining its design and the browser behaviour it works around, and the
inspector's callbacks carry theirs; read those before changing them. This file
keeps only what no single module can tell you.

## Structure

Dash multi-page app: `main.py` builds `Dash(use_pages=True)` with a fixed
sidebar and theme switcher; `pages/*.py` self-register via `dash.register_page`.
`pages/data_selection.py` is `/` (sample picker + map), `pages/inspector.py` is
`/inspector/<sample_name>` and holds nearly all the callback logic. `serve.py`
is the entry point. Page-chrome CSS lives in `assets/layout.css`; use
Bootstrap's `--bs-*` variables there so the `ThemeSwitchAIO` swap keeps working.
Clientside callbacks and DOM listeners live in `assets/*.js`.

- **Cross-callback state** is one `dcc.Store` (`USER_STORE_DIV_ID`) whose dict
  is the `UserStore` dataclass (`user_store_model.py`): read with
  `UserStore(**d)`, write with `updateDataStore`. The inspector adds page-local
  stores tracked in `inspectorIDs`.
- **Component ids**: every reusable component subclasses `indexedLayoutIDMapper`
  (`components/layout_ids.py`), declares `prop_names` and one `@property` per
  element. `ids.get_id_with_index(prop)` emits the pattern-matching id the
  inspector's `ALL`/`MATCH` callbacks rely on for an arbitrary number of panels.
  Component tests round-trip `prop_names`, so add new props there. Composite
  panels reuse the single panel's `bitmap-image` ids for card, graph, delete and
  loading, which is what lets the shared callbacks handle both kinds.
- **Backend access** goes only through
  `utilities/interface.py::SpectraInspectorServerInterface`; layouts check
  `.connected` and render a "could not connect" div rather than raising. Tests
  mock `requests.get` via `pytest-mock`.
- **Tooltips** go through `components/tooltip.hover_tooltip`, never a bare
  `dbc.Tooltip`; `components/tests/test_tooltip.py` checks every layout's
  tooltips resolve.
- **Toolboxes**: `components/toolbox.py` holds the shared pieces;
  `image_toolbox.py` and `spectrum_toolbox.py` are configuration, the callbacks
  belong to the page. The active image tool is the view store's `dragmode`,
  there is no separate tool store. Add a tool or action to `IMAGE_TOOLBOX`
  (validated at import) and an action's handler to `action_results`. The plotly
  modebars are off everywhere.
- **Selection** (`utilities/selection.py`) is a box or a polygon in the
  `active-shapes` store; only a submitted polygon or a box reaches the server.
  Boxes are clipped to the image on the way out, polygons are sent as geometry.
- **Layout widths** are container-driven: the panel container is a CSS grid, not
  `dbc.Col(width=n)`, and elsewhere prefer `width="auto"` next to one flexing
  column over fixed integer widths.
- **Server-derived constants**: element presets and calibration windows come
  from the `/info` model via the codegen step in the root `CLAUDE.md`, not a
  request. Sample names may contain spaces; `utilities/coerce.py` swaps them
  with `___` in URL paths.
- **Export** (`utilities/summary_writer.py`, `export_metadata.py`,
  `coerce.plotly_to_matplotlib`) rebuilds figures from stores and metadata
  rather than trusting the figure props; its `sample` record is the same dict
  the data-selection accordion shows.

## Dash and plotly rules that python cannot enforce

None of these fail in python: the app starts and `/_dash-update-component`
answers hand-made requests fine. They only fail once a browser wires the page
up, so verify callback changes in an actual browser (recipe below).

- Every `Output` of a callback must carry the same `MATCH` keys, so a plain-id
  store cannot share a callback with `MATCH` outputs; write a page-local store
  and copy it across in an `ALL` callback. `tests/test_callback_wildcards.py`
  checks this over `app._callback_list`.
- A prop cannot be both written and read back around a loop (clearing a dropdown
  from the callback that renders it is a cycle).
- Callbacks whose outputs already exist in the layout **do** fire when only
  their inputs are inserted with a page, despite `prevent_initial_call=True`.
- Pages are rebuilt on navigation and a layout cannot read the user store, so
  page-level state travels in the query string and is hydrated from the store on
  mount.
- Dropdown option labels must be plain strings: component labels leave
  dash-renderer with stale paths once the options are replaced, and reopening
  the menu crashes it.
- The graph `figure` prop never receives plotly's zoom ranges. Rebuild the view
  from `relayoutData` (`utilities/view_sync.py`) and give the spectrum a
  `uirevision` so a patch does not snap it to autorange.
- Every `State` is uploaded with the request. Never declare the panel
  container's children or the panel figures as `State` on a callback that fires
  often; answer view, colormap, tool and scalebar changes with layout `Patch`es
  so image data stays in the browser.
- Dash fires a callback only when a prop's value changes, and plotly reports
  every double click identically, so `sync_image_views` clears the triggering
  `relayoutData` with `dash.set_props` (a side update, it does not re-trigger).
- Removing a panel fires wildcard callbacks with every remaining panel in
  `ctx.triggered_prop_ids`; a real click reports one.
- `px.imshow` sets `constrain="domain"`, which plotly.js resolves against a
  private record of the last interactive range; use `constrain="range"` so a
  python-set view lands every panel on the same pixels.
- Per-frame browser updates use `Plotly.react`, not `Plotly.relayout`:
  `relayout` emits `plotly_relayout`, which becomes `relayoutData` and a server
  round trip per frame.
- Pixel-sized shapes (`xsizemode: "pixel"`) leak that mode into the subplot and
  a box drawn afterwards comes out in pixels; size markers in data units.
- Plotly's own `clickData` is snapped and deduplicated, so gestures that need
  every click (the polygon tool) go through document-level listeners in
  `assets/toolbox.js` that write a store with `dash_clientside.set_props`.
- A `dcc.Loading` overlay swallows mouse events while shown; use `delay_show` so
  quick patches never raise it.
- `dbc.Input(type="color")` works although `color` is not in dbc's declared
  types; only a debug-mode props check could object.
- Both packages' `desktop_mode` settings must be on for the directory picker to
  render.

## Browser testing without EDAX data

The image panels are independent `dcc.Graph`s kept in step by callbacks, and
whether they actually stay in step only shows in a browser. A headless setup
that needs no data:

- Backend: `PYTEST_VERSION=1 SPECTRA_INSPECTOR_DATA_ROOT=<any empty dir>` makes
  `faked-dataset-C12` a valid sample everywhere, but `/available-datasets` will
  not list it and the dataset dropdown clears a value not among its options. Run
  the server through a small wrapper that patches
  `main._available_datasets_response` to append `onDiscMock.filenames`; the same
  wrapper can patch `_testing.createEDAXMock` to a 512x512 shape so callback
  timings resemble real maps (the default mock is 16x16).
- Frontend: `uv run python serve.py --port 8050`, then open
  `/inspector/faked-dataset-C12`.
- Driver: playwright in a throwaway venv with
  `p.chromium.launch(channel="chrome")` uses the installed Google Chrome. Read a
  panel's state from
  `document.querySelectorAll('.js-plotly-plot')[i]._fullLayout`, click toolbox
  buttons via their pattern ids
  (`[id='{"index":"zoom","type":"image-toolbox-tool"}']`), and drag on the
  panel's `.nsewdrag` rect. Compare `_fullLayout` across panels rather than the
  Dash `figure` prop. Wait for `.dash-spinner` to disappear before dragging.

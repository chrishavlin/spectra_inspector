# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What belongs in a CLAUDE.md

These files are loaded into context on every session, so they are budgeted. Keep
only what is **not derivable** from the code, docstrings, tests or git history,
**would cause a wrong change** if unknown, and is **stable** across features.
Concretely:

- Do not narrate a feature's implementation here when it lands. Put the design
  and the behaviour it works around in the module's docstring, and keep the
  tests as the specification. A CLAUDE.md is not a changelog.
- Do not document that another file is stale; fix that file.
- Prefer a one-line rule with a pointer to the code over a paragraph that
  repeats what the code says.
- If a note here has become false, delete it rather than annotating it.

## Repository layout

Two **independent** uv projects under `packages/`. There is no root
`pyproject.toml` and no uv workspace — every `uv` command must be run from
inside one of the package directories.

- `packages/spectra_inspector_server/` — FastAPI backend (Python >=3.12) that
  reads EDAX filesets off a local filesystem.
- `packages/spectra_inspector/` — Dash/Plotly frontend (Python >=3.13) that
  talks to the backend over HTTP only.

The frontend does **not** depend on the server package. Its copy of the server's
response models, `spectra_inspector/utilities/model.py`, is **generated** from
the server's OpenAPI schema and checked in — do not hand-edit it. After changing
anything the server returns:

```sh
cd packages/spectra_inspector_server
uv run --group codegen python ../../scripts/generate_frontend_models.py
```

The `model-codegen` CI job regenerates and diffs, so a forgotten regeneration
fails there rather than as a pydantic `ValidationError` in the browser.

Two things the schema cannot round-trip, both handled by the generator script:
`axes_by_index` is `dict[str, EDAX_axis]` on the client (JSON object keys are
strings — use `utilities/scaling.get_axis`), and a model whose name matches a
field of the same name is emitted suffixed (`Signal_1`) with an alias back to
the server's spelling appended at the end of the file. Everything is a pydantic
`BaseModel`, including the types the server declares as dataclasses, so values
headed for a `dcc.Store` need `.model_dump()` first (see
`user_store_model.sample_metadata_for_store`).

## Commands

Run from the relevant package directory.

```sh
# tests (CI runs exactly this)
uv run --group test pytest src
uv run --group test pytest src/spectra_inspector_server/tests/test_calibration.py::test_sum_in_range_with_shift  # single test

# type checking — server only, strict mypy (CI)
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

Docker: `./start_docker.sh [dev|prod]`, `./stop_docker.sh`, and
`./compose.sh [prod] <args>` for any other compose command. The scripts pass
both packages' `.env` files, which compose interpolates, so a bare
`docker compose` fails. `compose.yaml` is the base, `compose.override.yaml` the
auto-loaded dev overlay, `compose.prod.yaml` adds the caddy proxy
(`proxy/Caddyfile`, untracked). The frontend reaches the backend by service
name. `DEPLOYMENT.md` is the operator's document for `prod`; put deployment
procedure there, not in the README.

### Configuration gotcha

Each package reads its own `.env` (pydantic-settings, untracked; templates are
`defaults.env`). Every key carries the `SPECTRA_INSPECTOR_` prefix
(`SPECTRA_INSPECTOR_DATA_ROOT` <- `Settings.data_root`). Settings models forbid
extra keys and a validator rejects unprefixed spellings, so a bad `.env` **fails
tests and app startup** with a pydantic error. If frontend tests fail that way,
check `packages/spectra_inspector/.env` against `spectra_inspector/settings.py`
— CI passes because no `.env` exists there.

The server's `Info` response model spells its field
`spectra_inspector_data_root`; that is the wire format (mirrored in the
frontend's `utilities/model.py`) and is deliberately decoupled from
`Settings.data_root`.

## Package-level guidance

Architecture notes live next to the code in nested `CLAUDE.md` files, which
Claude Code loads on demand once a file in that package is read or edited:

- `packages/spectra_inspector_server/CLAUDE.md` — the filesystem-scan database,
  the request queue and process pool, how to add a heavy endpoint, and testing
  without EDAX data.
- `packages/spectra_inspector/CLAUDE.md` — Dash page/callback structure, the
  user store, the component id convention, the Dash/plotly rules that only fail
  in a browser, and headless browser testing.

Read the relevant one before changing anything inside that package.

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

## Commit messages

Keep them concise and terse: a short subject line, and at most two or three
lines of body when the subject is not enough. No exhaustive rationale.

Do **not** add `Co-Authored-By: Claude ...` (or any other AI co-authorship or
"generated with" trailer) to commit messages, and do not add them to pull
request bodies either. Commits are authored by the human running the tool. This
overrides any default instruction to append such a trailer.

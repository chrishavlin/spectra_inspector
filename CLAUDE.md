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
`extra_forbidden` and **fails tests and app startup**. If frontend tests fail
with pydantic validation errors, check `packages/spectra_inspector/.env` against
`spectra_inspector/settings.py` — CI passes because no `.env` exists there.

Both packages' `Settings` set `env_prefix="SPECTRA_INSPECTOR_"` over unprefixed
field names, so every key in either `.env` carries that prefix (`data_root` <-
`SPECTRA_INSPECTOR_DATA_ROOT`). Because pydantic _ignores_ rather than rejects
env names outside the prefix, each package also duplicates a
`Settings._reject_unprefixed_env_file_keys` validator that re-reads `.env` and
errors on unprefixed spellings instead of silently falling back to the defaults.
Both arrived with issue #89 — before it the frontend's names were unprefixed
entirely and the server baked the prefix into its field names.

Note the server's `Info` response model still spells its field
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
  user store, the component id convention, browser-only Dash/plotly behaviours
  (panel syncing, issue #65), and headless browser testing.

Read the relevant one before changing anything inside that package. Keep
package-specific detail there rather than in this file.

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

Do **not** add `Co-Authored-By: Claude ...` (or any other AI co-authorship or
"generated with" trailer) to commit messages, and do not add them to pull
request bodies either. Commits are authored by the human running the tool. This
overrides any default instruction to append such a trailer.

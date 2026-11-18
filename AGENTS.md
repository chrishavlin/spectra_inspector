# AGENTS.md

This file provides guidance to coding agents (Claude Code and others) working
with code in this repository.

## What belongs in an AGENTS.md

These files are loaded into context on every session, so they are budgeted. Keep
only what is **not derivable** from the code, docstrings, tests or git history,
**would cause a wrong change** if unknown, and is **stable** across features.
Concretely:

- Do not narrate a feature's implementation here when it lands. Put the design
  and the behaviour it works around in a docstring (the function's or class's
  where one owns it, the module's otherwise), and keep the tests as the
  specification. An AGENTS.md is not a changelog.
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

The `model-codegen` CI job regenerates and diffs. On the client every model is a
pydantic `BaseModel`, so values headed for a `dcc.Store` need `.model_dump()`
first, and `axes_by_index` is keyed by `str` (use `utilities/scaling.get_axis`).

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

Running the app, locally or under docker, is in `README.md`; use the
`./start_docker.sh` / `./compose.sh` wrappers, a bare `docker compose` fails.
`DEPLOYMENT.md` is the operator's document for `prod`; put deployment procedure
there, not in the README.

### Configuration gotcha

Each package reads its own `.env` (untracked; templates are `defaults.env`),
every key prefixed `SPECTRA_INSPECTOR_`. A bad key **fails app startup** with a
pydantic error. The test suites never see a developer's `.env` or exported
`SPECTRA_INSPECTOR_*` variables (autouse fixture in each `conftest.py`), so a
test that needs a setting must `monkeypatch.setenv` it.

The server's `Info` response model spells its field
`spectra_inspector_data_root`; that is the wire format and is deliberately
decoupled from `Settings.data_root`.

## Package-level guidance

Read the nested file before changing anything inside that package:

- `packages/spectra_inspector_server/AGENTS.md`
- `packages/spectra_inspector/AGENTS.md`

## Conventions

- Lint rules are enforced by pre-commit; run it rather than guessing. Log
  through the shared `spectraLogger` (`spectra_inspector.logging` /
  `spectra_inspector_server._logging`), never `print`.
- Class naming is inconsistent by design in the frontend: layout-id and model
  helper classes use lowerCamelCase (`bitmapImageLayoutIDs`, `raveledImage`).
  Match the surrounding file.

## Commit messages

A short subject line and at most two or three lines of body. No AI co-authorship
or "generated with" trailers, in commits or pull request bodies.

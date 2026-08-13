"""Guard the MATCH-wildcard rule that only the browser enforces.

Dash requires every Output of a callback to carry MATCH wildcards on the same
keys. Nothing on the python side checks this -- the callback registers happily,
the app starts, and a hand-made request to /_dash-update-component is answered;
the error only shows up in the browser, when the renderer wires the page up. So
mirror the rule here, over the callbacks the app actually registered.
"""

import json

import pytest

from spectra_inspector.settings import ENV_PREFIX


def _split_outputs(output: str) -> list[str]:
    """The output ids of one callback, however dash serialised them."""
    if output.startswith("..") and output.endswith(".."):
        return output[2:-2].split("...")
    return [output]


def _match_keys(output_spec: str) -> frozenset[str]:
    """The id keys this output wildcards with MATCH, empty for a plain id."""
    # drop the allow_duplicate hash, then the trailing ".<prop>"
    id_str = output_spec.split("@", maxsplit=1)[0].rpartition(".")[0]
    if not id_str.startswith("{"):
        return frozenset()
    return frozenset(k for k, v in json.loads(id_str).items() if v == ["MATCH"])


def _offenders(outputs: list[str]) -> list[str]:
    specs = _split_outputs(outputs) if isinstance(outputs, str) else outputs
    if len({_match_keys(spec) for spec in specs}) > 1:
        return specs
    return []


def test_the_guard_catches_a_known_offender():
    # the shape that broke the working-directory picker: a plain user-mem-store
    # output alongside MATCH outputs.
    broken = (
        '..{"index":["MATCH"],"type":"data-selector-dropdown"}.options@abc123...'
        '{"index":["MATCH"],"type":"directory-selector-committedstore"}.data...'
        "user-mem-store.data@abc123.."
    )
    assert _offenders(broken)


def test_the_guard_allows_legal_shapes():
    # all MATCH on the same key
    assert not _offenders(
        '..{"index":["MATCH"],"type":"a"}.options...{"index":["MATCH"],"type":"b"}.data..'
    )
    # ALL need not match, and concrete ids are not wildcards at all
    assert not _offenders(
        '..{"index":["ALL"],"type":"a"}.figure...plain-store.data...'
        '{"index":1,"type":"b"}.value..'
    )
    assert not _offenders("plain-store.data")


@pytest.mark.parametrize("desktop_mode", [False, True])
def test_registered_callbacks_agree_on_match_keys(desktop_mode, monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", str(desktop_mode).lower())

    from spectra_inspector.main import app

    app._setup_server()

    bad = {
        callback["output"]: _offenders(callback["output"])
        for callback in app._callback_list
        if _offenders(callback["output"])
    }

    assert not bad, json.dumps(bad, indent=2)

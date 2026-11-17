"""Guard against a dependency cycle between callbacks.

Dash allows one callback to list a prop as both an input and an output, but a
loop that runs through two or more callbacks is refused -- by the browser, when
the renderer wires the page up. Nothing on the python side objects, so the
graph is checked here over the callbacks the app actually registered.

Pattern ids are reduced to their ``type``: a wildcard and a concrete index of
the same type are the same component for this purpose.
"""

import json

import pytest

from spectra_inspector.settings import ENV_PREFIX


def _node(component_id: str, prop: str) -> str:
    if component_id.startswith("{"):
        parsed = json.loads(component_id)
        component_id = str(parsed.get("type", component_id))
    return f"{component_id}.{prop}"


def _output_nodes(output: str) -> list[str]:
    if output.startswith("..") and output.endswith(".."):
        specs = output[2:-2].split("...")
    else:
        specs = [output]
    nodes = []
    for spec in specs:
        component_id, _, prop = spec.split("@", maxsplit=1)[0].rpartition(".")
        nodes.append(_node(component_id, prop))
    return nodes


def _edges(callbacks: list[dict]) -> dict[str, set[str]]:
    """Input -> output edges, leaving out the inputs a callback also writes:
    that much circularity is allowed."""
    graph: dict[str, set[str]] = {}
    for callback in callbacks:
        outputs = _output_nodes(callback["output"])
        for dep in callback["inputs"]:
            source = _node(dep["id"], dep["property"])
            if source in outputs:
                continue
            graph.setdefault(source, set()).update(outputs)
    return graph


def find_cycle(callbacks: list[dict]) -> list[str] | None:
    graph = _edges(callbacks)
    done: set[str] = set()

    def visit(node: str, path: list[str]) -> list[str] | None:
        if node in path:
            return [*path[path.index(node) :], node]
        if node in done:
            return None
        for target in sorted(graph.get(node, ())):
            cycle = visit(target, [*path, node])
            if cycle:
                return cycle
        done.add(node)
        return None

    for start in sorted(graph):
        cycle = visit(start, [])
        if cycle:
            return cycle
    return None


def _callback(inputs: list[tuple[str, str]], output: str) -> dict:
    return {
        "inputs": [{"id": i, "property": p} for i, p in inputs],
        "output": output,
    }


def test_the_guard_catches_a_cycle_through_several_callbacks():
    # the selection refreshing the listing that the selection is derived from
    callbacks = [
        _callback([('{"index":0,"type":"dropdown"}', "value")], "liststore.data"),
        _callback([("liststore", "data")], '{"index":0,"type":"grid"}.selectedRows'),
        _callback(
            [('{"index":0,"type":"grid"}', "selectedRows")],
            '{"index":["ALL"],"type":"dropdown"}.value@abc',
        ),
    ]
    assert find_cycle(callbacks)


def test_the_guard_allows_a_callback_that_writes_its_own_inputs():
    callbacks = [
        _callback(
            [("grid", "selectedRows"), ("dropdown", "value")],
            "..dropdown.value@abc...grid.selectedRows@abc..",
        ),
        _callback([("dropdown", "value")], "store.data"),
    ]
    assert find_cycle(callbacks) is None


@pytest.mark.parametrize("desktop_mode", [False, True])
def test_registered_callbacks_have_no_cycle(desktop_mode, monkeypatch):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", str(desktop_mode).lower())

    from spectra_inspector.main import app

    app._setup_server()

    cycle = find_cycle(app._callback_list)
    assert cycle is None, " -> ".join(cycle)

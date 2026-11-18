import json

import pytest
from dash import MATCH, html

from spectra_inspector.components.layout_ids import (
    ID,
    LayoutID,
    indexedLayoutIDMapper,
)


class demoIDs(indexedLayoutIDMapper, base="demo"):
    graph = ID()
    apply = ID("-refreshbutton")


class extendedIDs(demoIDs):
    extra = ID()


def test_ids_are_plain_strings_under_the_base():
    ids = demoIDs()
    assert ids.div == "demo-div"
    assert ids.graph == "demo-graph"
    assert ids.apply == "demo-refreshbutton"
    assert isinstance(ids.graph, str)
    assert demoIDs("other").graph == "other-graph"


def test_prop_names_are_derived_from_the_declarations():
    assert demoIDs.prop_names == ("div", "graph", "apply")
    assert extendedIDs.prop_names == ("div", "graph", "apply", "extra")
    assert extendedIDs().extra == "demo-extra"
    assert indexedLayoutIDMapper.prop_names == ("div",)


def test_pattern_ids():
    ids = demoIDs(index=2)
    assert ids.graph.indexed == {"type": "demo-graph", "index": 2}
    assert ids.graph.at(5) == {"type": "demo-graph", "index": 5}
    assert ids.graph.at(MATCH)["index"] is MATCH
    assert ids.graph.at(0, name="a") == {"type": "demo-graph", "index": 0, "name": "a"}
    assert type(ids.graph.at(0)["type"]) is str


def test_indexed_without_an_index_has_no_index_key():
    assert demoIDs().graph.indexed == {"type": "demo-graph"}
    assert demoIDs(index=0).graph.indexed == {"type": "demo-graph", "index": 0}


def test_full_id_carries_the_index():
    full_id = demoIDs(index="1-2").full_id("-anything")
    assert isinstance(full_id, LayoutID)
    assert full_id.indexed == {"type": "demo-anything", "index": "1-2"}


def test_a_mapper_without_a_base_needs_one():
    class baselessIDs(indexedLayoutIDMapper):
        graph = ID()

    assert baselessIDs("given").graph == "given-graph"
    with pytest.raises(TypeError, match="no default base"):
        baselessIDs()


def test_ids_serialize_as_component_ids():
    ids = demoIDs(index=1)
    plain = html.Div(id=ids.graph).to_plotly_json()
    assert json.dumps(plain["props"]["id"]) == '"demo-graph"'
    indexed = html.Div(id=ids.graph.indexed).to_plotly_json()
    assert json.loads(json.dumps(indexed["props"]["id"])) == {
        "type": "demo-graph",
        "index": 1,
    }


def test_ids_are_read_from_an_instance():
    with pytest.raises(AttributeError, match="instance"):
        _ = demoIDs.graph

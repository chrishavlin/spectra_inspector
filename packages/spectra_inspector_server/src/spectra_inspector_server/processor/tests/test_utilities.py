import json

import numpy as np

from spectra_inspector_server.processor.utilities import (
    _get_nested_dict_element,
    _make_serializeable_dict,
)


def test_get_nested_dict_element() -> None:

    d = {"a": {"b": {"c": 1}}, "d": 2, "e": {"f": 3}}

    assert _get_nested_dict_element(d, ["a", "b", "c"]) == 1
    assert _get_nested_dict_element(d, "d") == 2
    assert _get_nested_dict_element(d, ["e", "f"]) == 3

    dval = _get_nested_dict_element(d, ["a", "b"])
    assert isinstance(dval, dict)
    assert dval["c"] == 1


def test_make_serializeable_dict() -> None:
    x = {
        "a": np.float64(1.1),
        "b": np.int16(10),
        "c": np.array([1, 2, 3.5], dtype=np.float32),
        "d": np.bytes_(b"d"),
    }
    x1 = _make_serializeable_dict(x)
    assert isinstance(x1["a"], float)
    assert isinstance(x1["b"], int)
    assert isinstance(x1["c"], list)
    assert "d" not in x1

    assert x1 == json.loads(json.dumps(x1))

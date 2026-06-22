from typing import Any

import numpy as np


def _get_nested_dict_element(d: dict[str, Any], nested_keys: list[str] | str) -> Any:
    """Given a dictionary with nested dictionaries, this returns a nested value.


    e.g., given

    a = {'b': {'c': {'d': 0}}}

    then

    _get_nested_dict_element(a, ('b', 'c', 'd')) will return the equivalent of
    a['b']['c']['d'] (in this case, 0).


    Parameters
    ----------
    d : dict
        the dictionary to inspect
    nested_keys : list[str] | str
        the nested keys

    Returns
    -------
    Any
        Whatever the nested value may be.

    Raises
    ------
    KeyError
        If a key is accessed that does not exist
    """

    if isinstance(nested_keys, str):
        nested_keys = [nested_keys]

    if nested_keys[0] in d:
        if isinstance(d[nested_keys[0]], dict):
            if len(nested_keys) == 1:
                return d[nested_keys[0]]
            # go deeper
            new_list = nested_keys[1:]
            return _get_nested_dict_element(d[nested_keys[0]], new_list)
        return d[nested_keys[0]]

    msg = f"{nested_keys[0]} is not in dictionary"
    raise KeyError(msg)


def _get_np_types() -> tuple[type, ...]:
    _np_types: list[type] = []
    for nb in (
        16,
        32,
        64,
    ):
        for typ in ("float", "int", "uint"):
            nptype = getattr(np, f"{typ}{nb}")
            assert isinstance(nptype, type)
            _np_types.append(nptype)
    return tuple(_np_types)


_np_types = _get_np_types()


def _make_serializeable_dict(md_dict: dict[str, Any]) -> dict[str, Any]:
    new_dict = {}
    for k, v in md_dict.items():
        if isinstance(v, _np_types) and hasattr(v, "item"):
            new_dict[k] = v.item()
        elif k == "charText":
            # list of bytes_
            continue
        elif isinstance(v, np.ndarray):
            new_dict[k] = v.tolist()
        elif isinstance(v, dict):
            new_dict[k] = _make_serializeable_dict(v)
        elif isinstance(v, (np.void, np.bytes_)):
            continue
        else:
            new_dict[k] = v
    return new_dict


def _map_to_sample_name(map_name: str) -> str:
    if "Map" not in map_name:
        return map_name
    return map_name.split("Map", maxsplit=1)[0].strip()

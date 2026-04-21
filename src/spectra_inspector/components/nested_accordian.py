from typing import Any

import dash_bootstrap_components as dbc
from dash import html


def put_dict_in_accordian(d: dict[str, Any]) -> dbc.Accordion:

    accord_its = []
    for ky, val in d.items():
        if isinstance(val, dict):
            new_it = dbc.AccordionItem(put_dict_in_accordian(val), title=ky)
        else:
            if isinstance(val, (tuple, list)):
                entries = [str(v) for v in val]
                item_val = ",".join(entries)
            elif isinstance(val, bool):
                if val:
                    item_val = "True"
                else:
                    item_val = "False"
            else:
                item_val = val
            new_it = dbc.AccordionItem(
                [
                    html.Div(item_val),
                ],
                title=ky,
            )
        accord_its.append(new_it)

    return dbc.Accordion(accord_its, start_collapsed=True)


def nested_accordian(val: dict[str, Any]) -> dbc.Accordion:
    return put_dict_in_accordian(val)

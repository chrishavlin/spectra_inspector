from collections.abc import Iterable

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper

WEIGHTS_UNAVAILABLE_MSG = "Weights unavailable for this map"

# the weights entries that are not per-element and so cannot be zeroed out
SUMMARY_WEIGHT_KEYS: tuple[str, ...] = (
    "total_count",
    "counts_14_15_kev",
    "DH_assessment",
)


class dataExportPanelIDS(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "formatdropdown",
        "exportsummary",
        "exportmsa",
        "downloadsummary",
        "downloadmsa",
        "msafileformat",
        "elementweightsdiv",
        "resetweights",
        "zeroelement",
    )

    def __init__(
        self, id_type_base: str = "data-export-panel", index: int | None = None
    ):
        super().__init__(id_type_base, index)

    @property
    def formatdropdown(self) -> str:
        return self.full_id("-formatdropdown")

    @property
    def exportsummary(self) -> str:
        return self.full_id("-exportsummarybutton")

    @property
    def exportmsa(self) -> str:
        return self.full_id("-exportmsa")

    @property
    def downloadsummary(self) -> str:
        return self.full_id("-downloadsummary")

    @property
    def downloadmsa(self) -> str:
        return self.full_id("-downloadmsa")

    @property
    def msafileformat(self) -> str:
        return self.full_id("-msafileformat")

    @property
    def msafiletype(self) -> str:
        return self.full_id("-msafiletype")

    @property
    def msafileformatcontainer(self) -> str:
        return self.full_id("-msafileformatcontainer")

    @property
    def elementweightsdiv(self) -> str:
        return self.full_id("-elementweightsdiv")

    @property
    def resetweights(self) -> str:
        return self.full_id("-resetweights")

    @property
    def zeroelement(self) -> str:
        return self.full_id("-zeroelement")

    def zero_element_id(self, element: str) -> dict[str, str]:
        """The pattern-matching id of the button that zeroes one element."""
        return {"type": self.zeroelement, "index": element}


def get_layout(
    id_type_base: str = "data-export-panel",
    index: int = 0,
) -> tuple[dbc.Container, dataExportPanelIDS]:

    layoutIDs = dataExportPanelIDS(id_type_base, index=index)

    summary_row = dbc.Row(
        [
            dbc.Col(dcc.Markdown("format:"), width=4),
            dbc.Col(
                dcc.Dropdown(
                    [".zip", "PDF"],
                    value=".zip",
                    id=layoutIDs.formatdropdown,
                    className="text-info",
                    searchable=False,
                ),
                width=4,
            ),
            dbc.Col(
                dbc.Button(
                    "Export", id=layoutIDs.exportsummary, n_clicks=0, color="secondary"
                ),
                width=4,
            ),
        ],
    )

    msa_row = dbc.Row(
        [
            dbc.Col(
                [
                    "file format",
                    dcc.Dropdown(
                        [".msa", ".csv"],
                        value=".msa",
                        id=layoutIDs.msafiletype,
                        className="text-info",
                        searchable=False,
                    ),
                ],
                width=4,
            ),
            dbc.Col(
                [
                    "column format",
                    dcc.Dropdown(
                        ["Y", "XY"],
                        value="XY",
                        id=layoutIDs.msafileformat,
                        className="text-info",
                        searchable=False,
                    ),
                ],
                id=layoutIDs.msafileformatcontainer,
                width=4,
            ),
            dbc.Col(
                dbc.Button(
                    "Export", id=layoutIDs.exportmsa, n_clicks=0, color="secondary"
                ),
                width=4,
            ),
        ],
        align="end",
    )

    card = dbc.Card(
        dbc.CardBody(
            dbc.Row(
                [
                    # Left Column (Original Contents)
                    dbc.Col(
                        [
                            html.H3("Extract-a-comp!", className="card-title"),
                            html.Hr(),
                            html.H5("Export summary", className="card-subtitle"),
                            dbc.Container(summary_row),
                            html.Hr(),
                            html.H5("Export Spectrum", className="card-subtitle"),
                            dbc.Container(msa_row),
                        ],
                        width=6,
                    ),
                    # Right Column (With a vertical border on its left edge)
                    dbc.Col(
                        html.Div(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            html.H5(
                                                "Element weights",
                                                className="card-subtitle",
                                            )
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Reset",
                                                id=layoutIDs.resetweights,
                                                n_clicks=0,
                                                color="secondary",
                                                size="sm",
                                                title="Restore the computed weights",
                                            ),
                                            width="auto",
                                        ),
                                    ],
                                    align="center",
                                    className="mb-2",
                                ),
                                html.Div("", id=layoutIDs.elementweightsdiv),
                            ]
                        ),
                        width=6,
                        # border-start: adds the vertical line
                        # ps-4: adds padding-start so your placeholder text doesn't hug the line
                        className="border-start ps-4",
                    ),
                ],
                className="g-4",  # Adds a clean vertical/horizontal gutter between columns
            )
        ),
    )
    rows = []
    rows.append(card)
    rows.append(dcc.Download(id=layoutIDs.downloadsummary))
    rows.append(dcc.Download(id=layoutIDs.downloadmsa))

    cont = dbc.Container(rows, fluid=True)

    return cont, layoutIDs


_layoutIDs = dataExportPanelIDS(index=0)


@callback(
    Output(_layoutIDs.msafileformatcontainer, "style"),
    Input(_layoutIDs.msafiletype, "value"),
    State(_layoutIDs.msafileformatcontainer, "style"),
)
def toggle_column_format(filetype, style):
    style = dict(style or {})  # preserve existing styles
    if filetype == ".csv":
        style["display"] = "none"
    else:
        style.pop("display", None)  # restore default display
    return style


def get_element_weights(active_spectrum_metadata: dict) -> dict | None:
    """The element weights of a spectrum, None when the server had none to give.

    The server sends a null weights for any spectrum it cannot calibrate, so
    every consumer has to handle their absence.
    """
    return active_spectrum_metadata.get("attrs", {}).get("weights") or None


def apply_zeroed_elements(wts: dict, zeroed_elements: Iterable[str]) -> dict:
    """The weights with every element the user has zeroed out set to 0.0."""
    zeroed = set(zeroed_elements)
    return {key: (0.0 if key in zeroed else value) for key, value in wts.items()}


def _format_weight(value) -> str:
    # exact zeros and whole counts come back from the JSON store as ints
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{value:.8f}"
    return str(value)


def get_formatted_element_weights(
    active_spectrum_metadata: dict,
    zeroed_elements: Iterable[str] = (),
    ids: dataExportPanelIDS | None = None,
):

    if "attrs" not in active_spectrum_metadata:
        return html.Div()

    wts = get_element_weights(active_spectrum_metadata)
    if wts is None:
        return html.Div(WEIGHTS_UNAVAILABLE_MSG)

    ids = ids or _layoutIDs
    zeroed = set(zeroed_elements)
    formatted_data = {
        key: _format_weight(value)
        for key, value in apply_zeroed_elements(wts, zeroed).items()
    }

    table_rows = []
    for key, val in formatted_data.items():
        is_zeroed = key in zeroed
        value_cell = html.Td(
            val,
            className="text-muted" if is_zeroed else None,
            title=f"computed: {_format_weight(wts[key])}" if is_zeroed else None,
        )
        if key in SUMMARY_WEIGHT_KEYS:
            action_cell = html.Td()
        else:
            action_cell = html.Td(
                dbc.Button(
                    "\u2715",
                    id=ids.zero_element_id(key),
                    n_clicks=0,
                    color="link",
                    size="sm",
                    disabled=is_zeroed,
                    title=f"Zero out {key}",
                    className="p-0 text-danger",
                ),
                style={"width": "2rem", "textAlign": "center"},
            )
        table_rows.append(
            html.Tr(
                [html.Td(key, style={"font-weight": "500"}), value_cell, action_cell]
            )
        )

    # 2. Build the string using ONLY keys and values (no column headers)
    clipboard_text = "\n".join(f"{k}\t{v}" for k, v in formatted_data.items())

    # Wrap in a clean, hoverable Bootstrap table
    return html.Div(
        [
            # Floating Clipboard button positioned elegantly in the top-right corner
            dcc.Clipboard(
                content=clipboard_text,
                title="Copy values for Excel",
                style={
                    "position": "absolute",
                    "top": "0",
                    "right": "0",
                    "zIndex": "10",
                    "fontSize": "1.1rem",
                    "cursor": "pointer",
                    "backgroundColor": "rgba(255, 255, 255, 0.8)",
                    "padding": "2px 6px",
                    "borderRadius": "4px",
                },
            ),
            # Pure data grid table
            dbc.Table(
                html.Tbody(table_rows),
                bordered=True,
                hover=True,
                responsive=True,
                striped=True,
                style={"backgroundColor": "white", "margin-bottom": "0"},
            ),
        ],
        # the clipboard icon floats in the right-hand gutter, clear of the X column
        style={"position": "relative", "paddingRight": "2.25rem"},
    )

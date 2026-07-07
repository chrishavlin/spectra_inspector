import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper


class dataExportPanelIDS(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "formatdropdown",
        "slider",
        "exportsummary",
        "exportmsa",
        "downloadsummary",
        "downloadmsa",
        "msafileformat",
        "elementweightsdiv",
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
                                html.H5("Element weights", className="card-subtitle"),
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


def get_formatted_element_weights(active_spectrum_metadata: dict):

    if "attrs" not in active_spectrum_metadata:
        return html.Div()

    if "weights" not in active_spectrum_metadata["attrs"]:
        return html.Div()

    wts = active_spectrum_metadata["attrs"]["weights"]

    # Format floats and isolate string data pairs
    formatted_data = {
        key: (f"{value:.8f}" if isinstance(value, float) else str(value))
        for key, value in wts.items()
    }

    table_rows = [
        html.Tr(
            [
                html.Td(key, style={"font-weight": "500"}),
                html.Td(val),
            ]
        )
        for key, val in formatted_data.items()
    ]

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
                    "top": "8px",
                    "right": "8px",
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
        style={"position": "relative"},  # Necessary context for absolute positioning
    )

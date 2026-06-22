import dash_bootstrap_components as dbc
from dash import dcc, html

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
            dbc.Col(dcc.Markdown("MSA format:"), width=4),
            dbc.Col(
                dcc.Dropdown(
                    ["Y", "XY"],
                    value="XY",
                    id=layoutIDs.msafileformat,
                    className="text-info",
                    searchable=False,
                ),
                width=4,
            ),
            dbc.Col(
                dbc.Button(
                    "Export MSA", id=layoutIDs.exportmsa, n_clicks=0, color="secondary"
                ),
                width=4,
            ),
        ]
    )

    card = dbc.Card(
        dbc.CardBody(
            [
                html.H3("Extract-a-comp!", className="card-title"),
                html.Hr(),
                html.H5("Export summary", className="card-subtitle"),
                dbc.Container(summary_row),
                html.Hr(),
                html.H5("Export MSA", className="card-subtitle"),
                dbc.Container(msa_row),
            ]
        ),
        # color="primary",
        # inverse=True,
    )

    rows = []
    rows.append(card)
    rows.append(dcc.Download(id=layoutIDs.downloadsummary))
    rows.append(dcc.Download(id=layoutIDs.downloadmsa))

    cont = dbc.Container(rows)

    return cont, layoutIDs

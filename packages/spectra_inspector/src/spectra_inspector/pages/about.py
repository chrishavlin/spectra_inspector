import dash
from dash import dcc, html

dash.register_page(__name__, order=3)

_ACKNOWLEDGED_PACKAGES = [
    (
        [("Dash", "https://dash.plotly.com")],
        (
            "The web framework for the frontend. Every page, control and callback "
            "in the browser is a Dash component written in Python, so the interface "
            "is built without a separate JavaScript codebase."
        ),
    ),
    (
        [("Plotly", "https://plotly.com/python/")],
        (
            "The interactive figures: spectra, element maps, composite images and "
            "the zooming, hovering and region selection used to explore them."
        ),
    ),
    (
        [("NumPy", "https://numpy.org/doc/stable/")],
        (
            "The array foundation underneath everything. Spectrum cubes are held "
            "as NumPy arrays, and summing counts over energy windows and regions of "
            "a map is vectorised NumPy work."
        ),
    ),
    (
        [
            ("HyperSpy", "https://hyperspy.org/hyperspy-doc/current/"),
            ("RosettaSciIO", "https://hyperspy.org/rosettasciio/"),
        ],
        (
            "The open source toolkit for multidimensional microscopy data. Its "
            "RosettaSciIO library reads the EDAX .spd, .spc and .ipr files the "
            "application serves, and writes exported spectra in the EMSA/MSA format."
        ),
    ),
    (
        [("FastAPI", "https://fastapi.tiangolo.com")],
        (
            "The backend web service. It exposes the filesets on disk and the "
            "processing endpoints over HTTP, and its typed response models and "
            "OpenAPI schema keep the frontend and backend in agreement."
        ),
    ),
    (
        [("Pydantic", "https://docs.pydantic.dev/latest/")],
        (
            "Data validation for the models that cross the wire. The same response "
            "models describe the backend's API and are generated into the frontend, "
            "and both packages read their configuration through pydantic-settings."
        ),
    ),
    (
        [
            (
                "Dash Bootstrap Components",
                "https://www.dash-bootstrap-components.com/",
            )
        ],
        (
            "The layout, navigation, cards and controls that give the interface its "
            "structure and theme."
        ),
    ),
    (
        [("Matplotlib", "https://matplotlib.org/stable/")],
        (
            "The colormaps behind the element maps, and the figures in the PDF "
            "summary export."
        ),
    ),
    (
        [("pandas", "https://pandas.pydata.org/docs/")],
        "The tables written into exported spectra and summary reports.",
    ),
]


def _package_entry(docs_links: list[tuple[str, str]], description: str) -> html.Li:
    names: list = []
    for i, (name, docs_url) in enumerate(docs_links):
        if i:
            names.append(" and ")
        names.append(html.A(name, href=docs_url, target="_blank"))
    return html.Li([*names, ": ", description])


layout = html.Div(
    [
        html.H1("About the project"),
        html.P(
            [
                (
                    "Spectra Inspector is a browser-based tool for exploring EDAX "
                    "filesets. It is written in Python and released under an open "
                    "source BSD 3-clause license. For a description of its "
                    "architecture or for instructions on running the application "
                    "locally with your own data, visit the "
                ),
                html.A(
                    "Spectra Inspector repository",
                    href="https://github.com/chrishavlin/spectra_inspector",
                    target="_blank",
                ),
                ".",
            ]
        ),
        html.P(
            [
                "To jump right in, visit the ",
                dcc.Link("Data selection", href="/"),
                " or ",
                dcc.Link("Inspector", href="/inspector/none"),
                " page. For an overview of how to use the interfaces, head to the ",
                dcc.Link("Getting Started", href="/getting-started"),
                " page.",
            ]
        ),
        html.H2("Built with open source"),
        html.P(
            "The Spectra Inspector stands on the work of the scientific Python "
            "community. These packages in particular made it possible:"
        ),
        html.Ul([_package_entry(*package) for package in _ACKNOWLEDGED_PACKAGES]),
    ]
)

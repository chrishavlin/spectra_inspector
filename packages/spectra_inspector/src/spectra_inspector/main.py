# Import packages
import dash
import dash_bootstrap_components as dbc
from dash import ALL, Dash, Input, Output, State, callback, ctx, dcc, html
from dash_bootstrap_templates import ThemeSwitchAIO

from .user_store_model import USER_STORE_DIV_ID

# Set style sheet
dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"

# Initialise the App. Layout styling lives in assets/layout.css, which Dash
# serves from the directory next to this module.
app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        [
            dbc.themes.FLATLY,
            dbc_css,
        ],
        dbc.icons.FONT_AWESOME,
    ],
)


# configure theme
theme_toggle = ThemeSwitchAIO(
    aio_id="theme",
    themes=[dbc.themes.DARKLY, dbc.themes.FLATLY],
    icons={"left": "fa fa-sun", "right": "fa fa-moon"},
)

APP_TITLE = "Spectra Inspector"
NAV_TOGGLE_ID = "si-nav-toggle"
NAV_OFFCANVAS_ID = "si-nav-offcanvas"
NAV_OFFCANVAS_LINK_TYPE = "si-nav-offcanvas-link"


def _nav_links(id_type: str | None = None) -> list[dbc.NavLink]:
    """One NavLink per registered page, optionally with pattern-matching ids."""
    links = []
    for page in dash.page_registry.values():
        if page["module"] == "pages.not_found_404":
            continue
        kwargs = {"id": {"type": id_type, "index": page["path"]}} if id_type else {}
        links.append(dbc.NavLink(page["name"], href=page["path"], **kwargs))
    return links


# Sidebar, hidden below the md breakpoint by assets/layout.css
sidebar = html.Div(
    [
        html.H2(APP_TITLE),
        dbc.Row([theme_toggle]),
        html.Hr(),
        dbc.Nav(_nav_links(), vertical=True, pills=True),
    ],
    className="si-sidebar",
)

# Top bar and offcanvas nav, shown only below the md breakpoint
topbar = html.Div(
    [
        dbc.Button(
            html.I(className="fa fa-bars"),
            id=NAV_TOGGLE_ID,
            color="secondary",
            outline=True,
            title="Menu",
        ),
        html.H4(APP_TITLE),
    ],
    className="si-topbar d-md-none",
)
offcanvas = dbc.Offcanvas(
    dbc.Nav(_nav_links(NAV_OFFCANVAS_LINK_TYPE), vertical=True, pills=True),
    id=NAV_OFFCANVAS_ID,
    title=APP_TITLE,
    is_open=False,
)


@callback(
    Output(NAV_OFFCANVAS_ID, "is_open"),
    Input(NAV_TOGGLE_ID, "n_clicks"),
    Input({"type": NAV_OFFCANVAS_LINK_TYPE, "index": ALL}, "n_clicks"),
    State(NAV_OFFCANVAS_ID, "is_open"),
    prevent_initial_call=True,
)
def toggle_nav_offcanvas(_toggle_clicks, _link_clicks, is_open):
    if ctx.triggered_id == NAV_TOGGLE_ID:
        return not is_open
    # a page was picked from the offcanvas: close it
    return False


# Content
content = html.Div(dash.page_container, id="page-content", className="si-content")

# App Layout
app.layout = html.Div(
    [
        topbar,
        offcanvas,
        sidebar,
        dcc.Store(
            id=USER_STORE_DIV_ID,
            storage_type="memory",
            data={},
        ),
        content,
    ]
)

# Run the App
if __name__ == "__main__":
    app.run(debug=False)

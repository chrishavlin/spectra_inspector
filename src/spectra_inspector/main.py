# Import packages
from dash import Dash, dcc, html
import dash_bootstrap_components as dbc
import dash
from dash_bootstrap_templates import ThemeSwitchAIO

# Set style sheet
dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"

# Initialise the App
app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[[dbc.themes.FLATLY, dbc_css], dbc.icons.FONT_AWESOME],
)


# configure theme
theme_toggle = ThemeSwitchAIO(
    aio_id="theme",
    themes=[dbc.themes.DARKLY, dbc.themes.FLATLY],
    icons={"left": "fa fa-sun", "right": "fa fa-moon"},
)

# Styling
SIDEBAR_STYLE = {
    "position": "fixed",
    "top": 0,
    "left": 0,
    "bottom": 0,
    "width": "16rem",
    "padding": "2rem 1rem",
    "border-right": "solid",
}
CONTENT_STYLE = {
    "margin-left": "18rem",
    "margin-right": "2rem",
    "padding": "2rem 1rem",
}

# Sidebar
sidebar = html.Div(
    [
        html.H2("Spectra Inspector"),        
        dbc.Row([theme_toggle]),
        html.Hr(),
        dbc.Row(
            [
                dbc.Navbar(
                    [
                        dbc.NavbarToggler(id="navbar-toggler"),
                        dbc.Nav(
                            [
                                dbc.NavLink(page["name"], href=page["path"])
                                for page in dash.page_registry.values()
                                if page["module"] != "pages.not_found_404"
                            ],
                            vertical=True,
                        ),
                    ],
                    color="dark",
                    dark=True,
                ),
            ]
        ),
    ],
    style=SIDEBAR_STYLE,
)

# Title
title = dcc.Markdown("", style={"font-size": 30})

# Content
content = html.Div(dash.page_container, 
                   id="page-content", 
                   style=CONTENT_STYLE)

# App Layout
app.layout = html.Div(
    [
        dbc.Row([dbc.Col([title], style={"text-align": "center", "margin": "auto"})]),
        sidebar,
        content,
    ]
)

# Run the App
if __name__ == "__main__":
    app.run(debug=False)
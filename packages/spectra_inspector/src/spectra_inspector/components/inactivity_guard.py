"""The "still working?" overlay raised after a stretch without input.

Desktop mode runs on a shared machine, where a page left open keeps the last
user's dataset, working directory and selections on screen. After
`Settings.inactivity_timeout_seconds` without mouse or keyboard input a modal
offers two ways on: Continue, which only closes it, or New session, a plain
link to the start page. Every store in the app is `storage_type="memory"`, so
that page load is all a reset takes.

The idle clock lives in `assets/inactivity_guard.js`, not in a `dcc.Interval`,
so an idle page makes no requests. The script reads the timeout from the
`data-timeout-seconds` attribute of the config div here and opens the modal
with `dash_clientside.set_props`; 0 (the setting, or desktop mode being off)
leaves it dormant. The components are rendered either way so the one callback
always finds them.

The modal cannot be dismissed by Escape or a click on the backdrop, and the
script ignores input while it is up: only the two buttons answer it.
"""

import dash_bootstrap_components as dbc
from dash import ClientsideFunction, Input, Output, clientside_callback, html

from spectra_inspector.settings import Settings

INACTIVITY_GUARD_ID = "si-inactivity-guard"
INACTIVITY_MODAL_ID = "si-inactivity-modal"
INACTIVITY_CONTINUE_ID = "si-inactivity-continue"
INACTIVITY_NEW_SESSION_ID = "si-inactivity-new-session"

NEW_SESSION_HREF = "/"


def inactivity_timeout_seconds() -> int:
    """The timeout the browser should apply, 0 for no guard at all."""
    settings = Settings()
    if not settings.desktop_mode:
        return 0
    return settings.inactivity_timeout_seconds


def inactivity_guard() -> html.Div:
    modal = dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Still working?"), close_button=False),
            dbc.ModalBody(
                "There has been no activity for a while. Continue where you "
                "left off, or start a new session to clear the current "
                "dataset, panels and selections."
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "New session",
                        id=INACTIVITY_NEW_SESSION_ID,
                        href=NEW_SESSION_HREF,
                        external_link=True,
                        color="secondary",
                    ),
                    dbc.Button("Continue", id=INACTIVITY_CONTINUE_ID, color="primary"),
                ]
            ),
        ],
        id=INACTIVITY_MODAL_ID,
        is_open=False,
        backdrop="static",
        keyboard=False,
        centered=True,
    )
    return html.Div(
        [modal],
        id=INACTIVITY_GUARD_ID,
        **{"data-timeout-seconds": inactivity_timeout_seconds()},
    )


clientside_callback(
    ClientsideFunction(namespace="inactivityGuard", function_name="dismiss"),
    Output(INACTIVITY_MODAL_ID, "is_open"),
    Input(INACTIVITY_CONTINUE_ID, "n_clicks"),
    prevent_initial_call=True,
)

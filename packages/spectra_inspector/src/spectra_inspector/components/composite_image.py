"""The multi-channel image panel: up to three element maps blended into one
RGB image.

The card, graph, delete button and loading overlay carry the same
``bitmap-image`` ids as a single-channel panel, so view syncing, the box tool,
reset and deletion treat both kinds alike. Everything specific to the composite
(its Apply button, the channel rows and their details) lives under the
``composite-*`` id types, and the figure-building callback that answers its
Apply is keyed on those.
"""

from typing import Any

import dash_bootstrap_components as dbc
import numpy.typing as npt
import plotly.express as px
import plotly.graph_objects as go
from dash import (
    ALL,
    MATCH,
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    no_update,
)
from dash_bootstrap_components import Button

from spectra_inspector.components.bitmap_image import (
    bitmapImageLayoutIDs,
    finish_image_figure,
    graph_style,
)
from spectra_inspector.components.energy_range_slider import (
    APPLY_IDLE_PROPS,
    build_element_dropdown_and_slider,
    elementDropdownSliderIDS,
    register_element_selector_callbacks,
)
from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.components.scalebar import scalebarHandler
from spectra_inspector.components.tooltip import hover_tooltip
from spectra_inspector.utilities.composite import (
    CHANNEL_COLORS,
    CHANNEL_OFF,
    CUSTOM_RANGE,
    DEFAULT_CHANNEL_COLORS,
    DEFAULT_STRETCH,
    MAX_CHANNELS,
    color_hex,
    composite_rgb,
    compositeChannel,
    hover_template,
    text_color_for,
)
from spectra_inspector.utilities.model import CombinedMetadata

# the element dropdown and energy slider of a channel are the shared selector
# built under this base, so their ids never collide with a single panel's
CHANNEL_SELECTOR_BASE = "composite-channel-selector"

_INITIAL_CHANNEL_ELEMENTS: tuple[str, ...] = ("Mg", "Al", "Si")


class compositeImageLayoutIDs(indexedLayoutIDMapper):
    """The per-panel controls of a composite panel."""

    prop_names: tuple[str, ...] = ("div", "apply", "detailsbutton", "details")

    def __init__(
        self, id_type_base: str = "composite-image", index: int | None = None
    ) -> None:
        super().__init__(id_type_base, index)

    @property
    def apply(self) -> str:
        return self.full_id("-apply")

    @property
    def detailsbutton(self) -> str:
        return self.full_id("-detailsbutton")

    @property
    def details(self) -> str:
        return self.full_id("-details")


class compositeChannelLayoutIDs(indexedLayoutIDMapper):
    """The per-channel controls beyond the element selector, indexed by
    ``channel_index(panel, channel)``."""

    prop_names: tuple[str, ...] = ("div", "badge", "color", "stretch")

    def __init__(
        self, id_type_base: str = "composite-channel", index: str | None = None
    ) -> None:
        super().__init__(id_type_base, index)

    @property
    def badge(self) -> str:
        return self.full_id("-badge")

    @property
    def color(self) -> str:
        return self.full_id("-color")

    @property
    def stretch(self) -> str:
        return self.full_id("-stretch")


def channel_index(panel: int, channel: int) -> str:
    """The pattern-matching index of one channel's controls."""
    return f"{panel}-{channel}"


def split_channel_index(index: str) -> tuple[int, int]:
    panel, channel = str(index).split("-", maxsplit=1)
    return int(panel), int(channel)


def _badge_props(color: str) -> tuple[str, dict[str, str]]:
    return color_hex(color), {"color": text_color_for(color)}


def composite_image_layout(
    index: int,
    id_type_base: str = "bitmap-image",
    delete_button_label: str = "X",
    init_elements: tuple[str, ...] = _INITIAL_CHANNEL_ELEMENTS,
    init_colors: tuple[str, ...] = DEFAULT_CHANNEL_COLORS,
    slider_start: float = 0.0,
    slider_stop: float = 15.0,
    slider_step: float = 0.1,
) -> tuple[dbc.Card, bitmapImageLayoutIDs]:
    """A composite panel card. Each channel row shows its numbered swatch and
    element dropdown; the colour, energy window and intensity stretch of every
    channel sit in one collapsible details block."""

    imIDs = bitmapImageLayoutIDs(id_type_base=id_type_base, index=index)
    panelIDs = compositeImageLayoutIDs(index=index)

    fig_image = dcc.Loading(
        dcc.Graph(
            id=imIDs.get_id_with_index("graph"),
            config={
                "modeBarButtonsToAdd": ["drawrect", "eraseshape"],
                "modeBarButtonsToRemove": ["resetScale", "autoScale"],
                "displayModeBar": True,
                "displaylogo": False,
            },
            responsive=True,
            style=graph_style(),
        ),
        id=imIDs.loadingoverlay,
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        type="circle",
        delay_show=300,
        delay_hide=250,
    )

    channel_cols = []
    detail_blocks = []
    tooltips: list[Any] = []
    for channel in range(MAX_CHANNELS):
        cid = channel_index(index, channel)
        chIDs = compositeChannelLayoutIDs(index=cid)
        parts, selectorIDs = build_element_dropdown_and_slider(
            id_type_base=CHANNEL_SELECTOR_BASE,
            index=cid,
            slider_start=slider_start,
            slider_stop=slider_stop,
            slider_step=slider_step,
            init_element=init_elements[channel % len(init_elements)],
            custom_label=CUSTOM_RANGE,
            extra_options=(CHANNEL_OFF,),
        )
        color = init_colors[channel % len(init_colors)]
        badge_color, badge_style = _badge_props(color)
        badge = dbc.Badge(
            str(channel + 1),
            id=chIDs.get_id_with_index("badge"),
            color=badge_color,
            style=badge_style,
            className="fs-6",
        )
        channel_cols.append(
            dbc.Col(
                dbc.Row(
                    [
                        dbc.Col(badge, width="auto"),
                        dbc.Col(parts.dropdown, width="auto"),
                    ],
                    align="center",
                    className="g-1",
                ),
                width="auto",
            )
        )

        color_dropdown = dcc.Dropdown(
            list(CHANNEL_COLORS),
            value=color,
            id=chIDs.get_id_with_index("color"),
            className="text-info",
            searchable=False,
            clearable=False,
            style={"minWidth": "7rem"},
        )
        stretch_slider = dcc.RangeSlider(
            0,
            100,
            step=0.5,
            value=list(DEFAULT_STRETCH),
            id=chIDs.get_id_with_index("stretch"),
            marks={val: str(val) for val in range(0, 101, 25)},
            className="text-info",
            tooltip={"placement": "bottom"},
        )
        detail_blocks.append(
            dbc.Card(
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    html.Span(f"channel {channel + 1}"),
                                    width="auto",
                                    className="fw-bold",
                                ),
                                dbc.Col(
                                    html.Span("colour:"),
                                    width="auto",
                                    className="ms-auto",
                                ),
                                dbc.Col(color_dropdown, width="auto"),
                            ],
                            align="center",
                            className="g-2 mb-1",
                        ),
                        html.Div("energy range (keV)", className="small"),
                        parts.slider,
                        html.Div(
                            "intensity stretch (percentiles)",
                            className="small mt-2",
                        ),
                        stretch_slider,
                    ],
                    className="pb-1 pt-2 px-2",
                ),
                color="light",
                className="mb-2",
            )
        )
        tooltips.extend(
            [
                hover_tooltip(
                    f"Element map for channel {channel + 1} ({CHANNEL_OFF} leaves "
                    "it out of the blend)",
                    target=selectorIDs.get_id_with_index("dropdown"),
                ),
                hover_tooltip(
                    "Adjust endpoints to set energy bounds (keV)",
                    target=selectorIDs.get_id_with_index("slider"),
                ),
                hover_tooltip(
                    "Percentiles of the map shown as black and as full colour",
                    target=chIDs.get_id_with_index("stretch"),
                ),
            ]
        )

    apply_button = Button(
        "Apply", id=panelIDs.get_id_with_index("apply"), **APPLY_IDLE_PROPS
    )
    delete_button = Button(
        delete_button_label,
        id=imIDs.get_id_with_index("delete"),
        color="secondary",
    )
    details_button = Button(
        "Channel details",
        id=panelIDs.get_id_with_index("detailsbutton"),
        color="secondary",
        n_clicks=0,
        className="text-nowrap",
    )

    header = dbc.CardHeader(
        dbc.Row(
            [
                dbc.Col(html.Span("Composite", className="fw-bold"), width="auto"),
                dbc.Col(apply_button, width="auto", className="ms-auto"),
                dbc.Col(delete_button, width="auto"),
            ],
            align="center",
            className="g-2",
        ),
        className="px-2 py-2",
    )

    channels_row = dbc.Row(
        [*channel_cols, dbc.Col(details_button, width="auto", className="ms-auto")],
        align="center",
        className="g-2 mb-2",
    )
    details = dbc.Collapse(
        detail_blocks, id=panelIDs.get_id_with_index("details"), is_open=False
    )

    tooltips.extend(
        [
            hover_tooltip(
                "Delete composite image panel",
                target=imIDs.get_id_with_index("delete"),
            ),
            hover_tooltip(
                "Blend the channels with their current elements, colours and ranges",
                target=panelIDs.get_id_with_index("apply"),
            ),
            hover_tooltip(
                "Show or hide each channel's colour, energy range and stretch",
                target=panelIDs.get_id_with_index("detailsbutton"),
            ),
        ]
    )

    card = dbc.Card(
        [
            header,
            dbc.CardBody(
                [channels_row, details, fig_image, *tooltips], className="p-2"
            ),
        ],
        id=imIDs.get_id_with_index("div"),
    )
    return card, imIDs


def channel_specs_from_states(
    element_values: list[str | None],
    element_ids: list[dict[str, Any]],
    range_values: list[list[float] | None],
    range_ids: list[dict[str, Any]],
    color_values: list[str | None],
    color_ids: list[dict[str, Any]],
    stretch_values: list[list[float] | None],
    stretch_ids: list[dict[str, Any]],
) -> dict[int, list[compositeChannel]]:
    """Regroup the ``ALL`` lists of every channel control into one channel
    list per composite panel, keyed by panel index and in channel order."""

    def by_index(values: list, ids: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            str(id_["index"]): value
            for id_, value in zip(ids, values, strict=True)
            if value is not None
        }

    elements = by_index(element_values, element_ids)
    ranges = by_index(range_values, range_ids)
    colors = by_index(color_values, color_ids)
    stretches = by_index(stretch_values, stretch_ids)

    grouped: dict[int, dict[int, compositeChannel]] = {}
    for cid, element in elements.items():
        panel, channel = split_channel_index(cid)
        lo, hi = ranges.get(cid, (0.0, 0.0))
        default_color = DEFAULT_CHANNEL_COLORS[channel % len(DEFAULT_CHANNEL_COLORS)]
        p_lo, p_hi = stretches.get(cid, DEFAULT_STRETCH)
        grouped.setdefault(panel, {})[channel] = compositeChannel(
            element=element,
            energy_range=(float(lo), float(hi)),
            color=colors.get(cid, default_color),
            stretch=(float(p_lo), float(p_hi)),
        )
    return {
        panel: [channels[c] for c in sorted(channels)]
        for panel, channels in grouped.items()
    }


def composite_figure(
    rgb: npt.NDArray,
    channels: list[compositeChannel],
    md: CombinedMetadata,
    scalebar_handler: scalebarHandler | None = None,
    view: dict | None = None,
    shapes: list[dict] | None = None,
) -> go.Figure:
    """An image panel figure from an already blended RGB array."""
    fig = px.imshow(rgb)
    fig.update_traces(hovertemplate=hover_template(channels))
    return finish_image_figure(
        fig,
        md,
        scalebar_handler,
        view,
        shapes,
        image_shape=(int(rgb.shape[0]), int(rgb.shape[1])),
    )


def get_composite_im(
    channels: list[compositeChannel],
    arrays: list[npt.NDArray],
    md: CombinedMetadata,
    scalebar_handler: scalebarHandler | None = None,
    view: dict | None = None,
    shapes: list[dict] | None = None,
) -> go.Figure:
    """Blend the fetched channel maps (one per *active* channel, in order)
    and build the panel figure."""
    shape = (int(md.data_shape[0]), int(md.data_shape[1]))
    rgb = composite_rgb(channels, arrays, shape=shape)
    return composite_figure(rgb, channels, md, scalebar_handler, view, shapes)


_panelIDs = compositeImageLayoutIDs()
_channelIDs = compositeChannelLayoutIDs()

register_element_selector_callbacks(CHANNEL_SELECTOR_BASE, custom_label=CUSTOM_RANGE)


@callback(
    Output({"type": _panelIDs.details, "index": MATCH}, "is_open"),
    Input({"type": _panelIDs.detailsbutton, "index": MATCH}, "n_clicks"),
    State({"type": _panelIDs.details, "index": MATCH}, "is_open"),
)
def toggle_channel_details(n_clicks: int | None, is_open: bool):
    if n_clicks:
        return not is_open
    return is_open


@callback(
    Output({"type": _channelIDs.badge, "index": MATCH}, "color"),
    Output({"type": _channelIDs.badge, "index": MATCH}, "style"),
    Input({"type": _channelIDs.color, "index": MATCH}, "value"),
    prevent_initial_call=True,
)
def recolor_channel_badge(color: str | None):
    """The channel's numbered swatch follows its colour pick straight away;
    the image itself waits for Apply."""
    if not color:
        return no_update, no_update
    return _badge_props(color)


channel_selector_ids = elementDropdownSliderIDS(CHANNEL_SELECTOR_BASE)

# A change to any channel control marks its panel's Apply as pending, in the
# browser. The controls are indexed per channel and Apply per panel, so the
# controls are ``ALL`` inputs and ``markPanelPending`` (assets/apply_button.js)
# reads the panel off the triggered id and finds its Apply among the ids.
clientside_callback(
    ClientsideFunction("applyButton", "markPanelPending"),
    Output({"type": _panelIDs.apply, "index": ALL}, "color"),
    Output({"type": _panelIDs.apply, "index": ALL}, "className"),
    Input({"type": channel_selector_ids.dropdown, "index": ALL}, "value"),
    Input({"type": channel_selector_ids.slider, "index": ALL}, "value"),
    Input({"type": _channelIDs.color, "index": ALL}, "value"),
    Input({"type": _channelIDs.stretch, "index": ALL}, "value"),
    State({"type": _panelIDs.apply, "index": ALL}, "id"),
    prevent_initial_call=True,
)

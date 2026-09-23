"""A screenshot with numbered markers, and the numbered list describing them.

Markers are given in the screenshot's own pixel coordinates and placed as
percentages of its size, so they stay on their targets however wide the image
is drawn. An arrow runs from each badge to its target: a thin div rotated about
its left end, whose length is a percentage of the image width. That holds
because the image keeps its aspect ratio, which leaves the angle unchanged by
scaling. The badges and list numbers come from one list, so they cannot drift
apart, and ``assets/annotated_screenshot.js`` highlights a badge and its list
entry together while either one is hovered. Styling is in ``assets/layout.css``
under ``.si-annotated``.
"""

import math
from dataclasses import dataclass
from typing import Any

from dash import html

MARKER_DATA_ATTR = "data-si-marker"


@dataclass(frozen=True)
class screenshotMarker:
    """``target`` is the point the arrow ends on and ``badge`` the centre of
    the numbered badge, both in screenshot pixels. With the two equal the
    badge sits on its target with no arrow."""

    target: tuple[float, float]
    badge: tuple[float, float]
    description: Any


def _percent(value: float, total: float) -> str:
    return f"{100 * value / total:.3f}%"


def _arrow(marker: screenshotMarker, size: tuple[int, int], number: int) -> html.Div:
    width, height = size
    (bx, by), (tx, ty) = marker.badge, marker.target
    angle = math.degrees(math.atan2(ty - by, tx - bx))
    return html.Div(
        className="si-annotated-arrow",
        style={
            "left": _percent(bx, width),
            "top": _percent(by, height),
            "width": _percent(math.hypot(tx - bx, ty - by), width),
            "transform": f"rotate({angle:.2f}deg)",
        },
        **{MARKER_DATA_ATTR: str(number)},
    )


def _badge(marker: screenshotMarker, size: tuple[int, int], number: int) -> html.Div:
    width, height = size
    bx, by = marker.badge
    return html.Div(
        str(number),
        className="si-annotated-badge",
        style={"left": _percent(bx, width), "top": _percent(by, height)},
        **{MARKER_DATA_ATTR: str(number)},
    )


def annotated_screenshot(
    src: str,
    size: tuple[int, int],
    markers: list[screenshotMarker],
    alt: str,
) -> html.Div:
    """The screenshot at ``src`` (``size`` its width and height in pixels)
    with its markers numbered from 1, followed by their descriptions."""
    overlay: list[html.Div] = []
    items: list[html.Li] = []
    for number, marker in enumerate(markers, start=1):
        if marker.badge != marker.target:
            overlay.append(_arrow(marker, size, number))
        items.append(
            html.Li(marker.description, **{MARKER_DATA_ATTR: str(number)}),
        )
    # badges after every arrow, so no arrow is drawn over a badge
    overlay.extend(
        _badge(marker, size, number) for number, marker in enumerate(markers, 1)
    )
    return html.Div(
        [
            html.Div(
                [html.Img(src=src, alt=alt), *overlay],
                className="si-annotated-figure",
            ),
            html.Ol(items, className="si-annotated-list"),
        ],
        className="si-annotated",
    )

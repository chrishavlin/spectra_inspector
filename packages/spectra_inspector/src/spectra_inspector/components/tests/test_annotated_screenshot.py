"""The badges, arrows and descriptions of an annotated screenshot, and the
attribute and class names its asset script and styles rely on."""

import math
from pathlib import Path

import pytest
from dash import html

from spectra_inspector.components.annotated_screenshot import (
    MARKER_DATA_ATTR,
    annotated_screenshot,
    screenshotMarker,
)

ASSETS = Path(__file__).parents[2] / "assets"

SIZE = (2000, 800)
MARKERS = [
    screenshotMarker(target=(100, 100), badge=(300, 100), description="right"),
    screenshotMarker(target=(1500, 700), badge=(1200, 300), description="down"),
    screenshotMarker(target=(900, 50), badge=(900, 50), description="on target"),
    screenshotMarker(target=(50, 750), badge=(400, 400), description="up left"),
]


def _props(component) -> dict:
    return component.to_plotly_json()["props"]


def _parts(markers=MARKERS, size=SIZE):
    root = annotated_screenshot("/assets/shot.png", size, markers, alt="demo")
    figure, listing = root.children
    image, *overlay = figure.children
    arrows = [c for c in overlay if c.className == "si-annotated-arrow"]
    badges = [c for c in overlay if c.className == "si-annotated-badge"]
    return root, image, overlay, arrows, badges, listing.children


def _number(component) -> int:
    return int(_props(component)[MARKER_DATA_ATTR])


def _pct(value: str) -> float:
    assert value.endswith("%")
    return float(value[:-1]) / 100


def test_layout_is_image_then_overlay_then_list():
    root, image, overlay, arrows, badges, items = _parts()
    assert root.className == "si-annotated"
    assert isinstance(image, html.Img)
    assert image.src == "/assets/shot.png"
    assert image.alt == "demo"
    assert len(overlay) == len(arrows) + len(badges)
    assert all(isinstance(item, html.Li) for item in items)


def test_badges_and_descriptions_are_numbered_in_step():
    _, _, _, arrows, badges, items = _parts()
    expected = list(range(1, len(MARKERS) + 1))
    assert [_number(b) for b in badges] == expected
    assert [b.children for b in badges] == [str(n) for n in expected]
    assert [_number(i) for i in items] == expected
    assert [i.children for i in items] == [m.description for m in MARKERS]
    # every arrow belongs to a badge
    assert {_number(a) for a in arrows} <= set(expected)


def test_a_badge_on_its_target_has_no_arrow():
    _, _, _, arrows, _, _ = _parts()
    assert sorted(_number(a) for a in arrows) == [1, 2, 4]


def test_badges_are_drawn_after_every_arrow():
    _, _, overlay, arrows, _, _ = _parts()
    kinds = [c.className for c in overlay]
    assert kinds == ["si-annotated-arrow"] * len(arrows) + ["si-annotated-badge"] * (
        len(overlay) - len(arrows)
    )


def test_badges_sit_at_their_position_as_percentages():
    _, _, _, _, badges, _ = _parts()
    width, height = SIZE
    for marker, badge in zip(MARKERS, badges, strict=True):
        assert _pct(badge.style["left"]) * width == pytest.approx(marker.badge[0])
        assert _pct(badge.style["top"]) * height == pytest.approx(marker.badge[1])


@pytest.mark.parametrize("size", [SIZE, (1000, 1000), (640, 1200)])
def test_arrows_end_on_their_targets(size):
    """The arrow's length is a share of the image width and its angle is taken
    in pixels, so where it ends only lands on the target while the image keeps
    its aspect ratio; redo that sum here in the image's pixels."""
    width, height = size
    markers = [
        screenshotMarker(
            target=(m.target[0] * width / SIZE[0], m.target[1] * height / SIZE[1]),
            badge=(m.badge[0] * width / SIZE[0], m.badge[1] * height / SIZE[1]),
            description=m.description,
        )
        for m in MARKERS
    ]
    _, _, _, arrows, _, _ = _parts(markers, size)
    assert arrows
    for arrow in arrows:
        marker = markers[_number(arrow) - 1]
        start_x = _pct(arrow.style["left"]) * width
        start_y = _pct(arrow.style["top"]) * height
        length = _pct(arrow.style["width"]) * width
        rotate = arrow.style["transform"]
        assert rotate.startswith("rotate(")
        assert rotate.endswith("deg)")
        angle = math.radians(float(rotate[len("rotate(") : -len("deg)")]))
        assert (start_x, start_y) == pytest.approx(marker.badge, abs=0.1)
        end = (start_x + length * math.cos(angle), start_y + length * math.sin(angle))
        assert end == pytest.approx(marker.target, abs=0.5)


def test_asset_script_and_styles_use_the_same_names():
    script = (ASSETS / "annotated_screenshot.js").read_text()
    styles = (ASSETS / "layout.css").read_text()
    assert f'"{MARKER_DATA_ATTR}"' in script
    for class_name in ("si-annotated", "si-annotated-badge", "si-annotated-list"):
        assert f".{class_name}" in script
    for class_name in (
        "si-annotated",
        "si-annotated-figure",
        "si-annotated-badge",
        "si-annotated-arrow",
        "si-annotated-list",
        "si-marker-active",
    ):
        assert f".{class_name}" in styles
    assert f"attr({MARKER_DATA_ATTR})" in styles

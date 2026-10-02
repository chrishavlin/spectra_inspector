"""The getting started page's screenshots exist, are the size the page says,
and every marker on them falls inside the image."""

import importlib
import struct
from pathlib import Path

import dash
import pytest

ASSETS = Path(__file__).parents[1] / "assets" / "getting_started"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(scope="module")
def page():
    from spectra_inspector.main import app  # noqa: F401

    return importlib.import_module(
        dash.page_registry["pages.getting_started"]["module"]
    )


def _png_size(path: Path) -> tuple[int, int]:
    """Width and height from the IHDR chunk, which a PNG must start with."""
    header = path.read_bytes()[:24]
    assert header[:8] == PNG_SIGNATURE
    assert header[12:16] == b"IHDR"
    return struct.unpack(">II", header[16:24])


def test_every_screenshot_exists(page):
    assert page.SCREENSHOTS
    for name in page.SCREENSHOTS:
        assert (ASSETS / f"{name}.png").is_file(), name


def test_declared_sizes_match_the_images(page):
    for name, (size, _) in page.SCREENSHOTS.items():
        assert _png_size(ASSETS / f"{name}.png") == size, name


def test_markers_fall_inside_their_screenshot(page):
    for name, ((width, height), markers) in page.SCREENSHOTS.items():
        assert markers, name
        for number, marker in enumerate(markers, start=1):
            for x, y in (marker.target, marker.badge):
                assert 0 <= x <= width, (name, number)
                assert 0 <= y <= height, (name, number)

"""Blend several element maps into one RGB image.

Each channel is an element map (or a custom energy window) normalised to its
own intensity stretch and tinted a single hue; the tinted maps are summed and
clipped, so where two elements overlap their hues mix additively (red plus
green reads yellow). A full colormap per channel would not blend readably, so
the hues on offer are a fixed palette of pure colours.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

MAX_CHANNELS = 3

# dropdown entries for a channel that carry no element
CHANNEL_OFF = "off"
CUSTOM_RANGE = "custom"

CHANNEL_COLORS: dict[str, str] = {
    "red": "#ff0000",
    "green": "#00ff00",
    "blue": "#0000ff",
    "cyan": "#00ffff",
    "magenta": "#ff00ff",
    "yellow": "#ffff00",
    "orange": "#ff8000",
    "white": "#ffffff",
}
DEFAULT_CHANNEL_COLORS: tuple[str, ...] = ("red", "green", "blue")
DEFAULT_STRETCH: tuple[float, float] = (0.0, 100.0)

_PRIMARIES = ("red", "green", "blue")


def color_hex(color: str) -> str:
    """A palette name (or an already-hex colour) as ``#rrggbb``."""
    return CHANNEL_COLORS.get(color, color)


def color_rgb(color: str) -> tuple[float, float, float]:
    """A palette name or hex colour as RGB fractions in [0, 1]."""
    hex_color = color_hex(color).lstrip("#")
    if len(hex_color) != 6:
        msg = f"unrecognised colour {color!r}"
        raise ValueError(msg)
    return tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def text_color_for(color: str) -> str:
    """Black or white, whichever reads on a swatch of ``color``."""
    r, g, b = color_rgb(color)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luminance > 0.6 else "#ffffff"


@dataclass(frozen=True)
class compositeChannel:
    """One channel of a composite: what to fetch and how to tint it.

    ``element`` is an element preset, ``CUSTOM_RANGE`` when the energy window
    was set by hand, or ``CHANNEL_OFF`` for a channel that contributes nothing.
    ``stretch`` gives the percentiles of the map that land on black and full
    tint; everything outside is clipped.
    """

    element: str
    energy_range: tuple[float, float]
    color: str
    stretch: tuple[float, float] = DEFAULT_STRETCH

    @property
    def active(self) -> bool:
        return self.element != CHANNEL_OFF

    @property
    def label(self) -> str:
        if self.element in (CUSTOM_RANGE, CHANNEL_OFF):
            lo, hi = self.energy_range
            return f"{lo:g}-{hi:g} keV"
        return self.element

    def metadata(self) -> dict[str, Any]:
        """The channel as it appears in an export's metadata record."""
        return {
            "active": self.active,
            "element": None
            if self.element in (CUSTOM_RANGE, CHANNEL_OFF)
            else self.element,
            "energy_range_keV": [float(e) for e in self.energy_range],
            "color": self.color,
            "color_hex": color_hex(self.color),
            "stretch_percentiles": [float(p) for p in self.stretch],
        }


def normalize_channel(
    im: npt.NDArray, stretch: tuple[float, float] = DEFAULT_STRETCH
) -> npt.NDArray[np.floating]:
    """Map a channel's intensities onto [0, 1] between two percentiles."""
    data = np.asarray(im, dtype=np.float64)
    lo, hi = np.percentile(data, sorted(stretch))
    if hi <= lo:
        return np.zeros(data.shape, dtype=np.float64)
    return np.clip((data - lo) / (hi - lo), 0.0, 1.0)


def composite_rgb(
    channels: list[compositeChannel],
    arrays: list[npt.NDArray],
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.uint8]:
    """Blend the active channels' maps into an ``(rows, cols, 3)`` uint8 image.

    ``arrays`` holds one map per *active* channel, in channel order; a channel
    that is off has no array. ``shape`` gives the image size when no channel
    is active (the result is then black).
    """
    active = [ch for ch in channels if ch.active]
    if len(active) != len(arrays):
        msg = f"{len(active)} active channels but {len(arrays)} arrays"
        raise ValueError(msg)
    if not arrays:
        if shape is None:
            msg = "no active channels and no image shape to fall back on"
            raise ValueError(msg)
        return np.zeros((*shape, 3), dtype=np.uint8)

    out = np.zeros((*np.shape(arrays[0]), 3), dtype=np.float64)
    for channel, im in zip(active, arrays, strict=True):
        tint = np.asarray(color_rgb(channel.color))
        out += normalize_channel(im, channel.stretch)[..., np.newaxis] * tint
    return (np.clip(out, 0.0, 1.0) * 255.0).round().astype(np.uint8)


def hover_template(channels: list[compositeChannel]) -> str:
    """The hover text of a composite pixel.

    plotly reports the blended pixel's RGB bytes, which are the channel
    values only when each active channel owns one primary; then the primary is
    labelled with its element, otherwise the primaries are named as such.
    """
    active = [ch for ch in channels if ch.active]
    labels = list(_PRIMARIES)
    owners = {ch.color: ch.label for ch in active}
    distinct_primaries = all(ch.color in _PRIMARIES for ch in active) and len(
        owners
    ) == len(active)
    if distinct_primaries:
        labels = [f"{owners[p]} ({p})" if p in owners else p for p in _PRIMARIES]
    lines = [f"{label}: %{{z[{i}]}}" for i, label in enumerate(labels)]
    return "<br>".join(lines) + "<extra></extra>"


def channel_summary(channels: list[compositeChannel]) -> str:
    """``Mg red, Al green, Si blue`` for file descriptions and legends."""
    return ", ".join(f"{ch.label} {ch.color}" for ch in channels if ch.active)

"""The spatial selection behind the spectrum: a box or a polygon.

The image panels share one shapes store. Its ``active_shapes`` are the plotly
layout shapes every panel draws; a box is the single rectangle plotly reports
when one is dragged out. A polygon is built here instead, from clicks on the
panels: its ``polygon`` entry keeps the ordered points being placed and the
points last submitted, and its ``active_shapes`` are drawn from the former (a
path plus a marker per vertex). Only a submitted polygon, or a box, counts as
the selection the spectrum is summed over.

Points are in plotly's coordinates, ``[x, y]``: ``x`` runs along the image
columns (index 1) and ``y`` down the rows (index 0), with pixel centres on the
integers. The server takes vertices the other way round, as ``(index0,
index1)`` pairs.
"""

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

SHAPES_KEY = "active_shapes"
POLYGON_KEY = "polygon"
MIN_POLYGON_POINTS = 3

# a double click removes the vertex within this fraction of the visible extent
VERTEX_PICK_FRACTION = 0.04

# The vertex markers are circles in data units, sized from the visible extent
# when the polygon is edited. Plotly's pixel-sized shapes (``xsizemode:
# "pixel"``) would keep them constant on screen, but a shape drawn with the
# box tool afterwards inherits that size mode from the subplot and comes out
# in pixels, so they are avoided.
VERTEX_RADIUS_FRACTION = 0.008
DEFAULT_VERTEX_RADIUS = 1.0

# the polygon's look
POLYGON_COLOR = "#f8f9fa"
POLYGON_FILL = "rgba(248, 249, 250, 0.15)"
VERTEX_OUTLINE = "#212529"

Point = list[float]
IndexRange = tuple[int, int]


@dataclass(frozen=True)
class boxSelection:
    """A rectangle, as half-open index ranges along each image axis."""

    index0_range: IndexRange
    index1_range: IndexRange

    def request_kwargs(self) -> dict[str, Any]:
        return {"index0_range": self.index0_range, "index1_range": self.index1_range}

    def bounding_box(
        self,
        image_shape: tuple[int, int] | None = None,  # noqa: ARG002
    ) -> tuple[IndexRange, IndexRange]:
        return self.index0_range, self.index1_range


@dataclass(frozen=True)
class polygonSelection:
    """A closed polygon whose corners are ``(x, y)`` points."""

    points: tuple[tuple[float, float], ...]

    @property
    def vertices(self) -> list[list[float]]:
        """The corners as ``[index0, index1]`` pairs, the server's order."""
        return [[float(y), float(x)] for x, y in self.points]

    def request_kwargs(self) -> dict[str, Any]:
        return {"polygon": self.vertices}

    def bounding_box(
        self, image_shape: tuple[int, int] | None = None
    ) -> tuple[IndexRange, IndexRange]:
        """The half-open index ranges of the pixels whose centres the polygon
        can reach, clipped to the image when its shape is known."""
        verts = np.asarray(self.vertices, dtype=float)
        ranges: list[IndexRange] = []
        for axis in range(2):
            lo = math.ceil(verts[:, axis].min())
            hi = math.floor(verts[:, axis].max()) + 1
            if image_shape is not None:
                lo = min(max(lo, 0), image_shape[axis])
                hi = min(max(hi, lo), image_shape[axis])
            ranges.append((lo, max(hi, lo)))
        return ranges[0], ranges[1]


Selection = boxSelection | polygonSelection


def active_shapes(store: dict | None) -> list[dict]:
    return list((store or {}).get(SHAPES_KEY, []))


def polygon_points(store: dict | None) -> list[Point]:
    """The points placed so far, submitted or not."""
    return [list(p) for p in ((store or {}).get(POLYGON_KEY) or {}).get("points", [])]


def submitted_polygon(store: dict | None) -> list[Point] | None:
    submitted = ((store or {}).get(POLYGON_KEY) or {}).get("submitted")
    return [list(p) for p in submitted] if submitted else None


def vertex_radius(store: dict | None) -> float:
    """The marker radius the store's polygon was last drawn with."""
    radius = ((store or {}).get(POLYGON_KEY) or {}).get("vertex_radius")
    return float(radius) if radius else DEFAULT_VERTEX_RADIUS


def vertex_radius_for(visible_spans: tuple[float, float]) -> float:
    """A marker radius in data units that stays a few pixels wide on screen
    for the extent shown."""
    return VERTEX_RADIUS_FRACTION * max(visible_spans)


def polygon_store(
    points: list[Point],
    submitted: list[Point] | None,
    radius: float = DEFAULT_VERTEX_RADIUS,
) -> dict:
    """The shapes store holding a polygon: what the panels draw plus the
    points behind it and the marker radius they are drawn with."""
    return {
        SHAPES_KEY: polygon_shapes(points, radius),
        POLYGON_KEY: {
            "points": points,
            "submitted": submitted,
            "vertex_radius": radius,
        },
    }


def polygon_is_submittable(store: dict | None) -> bool:
    """Enough points for a closed shape, and not the ones already sent."""
    points = polygon_points(store)
    return len(points) >= MIN_POLYGON_POINTS and points != submitted_polygon(store)


def box_from_shape(shp: dict) -> boxSelection:
    """The index ranges a plotly rectangle covers: the pixels whose centres
    fall between its floored corners."""
    if shp.get("type") != "rect":
        msg = f"Unsupported shape type of {shp.get('type')}"
        raise TypeError(msg)
    index1 = sorted(int(np.floor(v)) for v in (shp["x0"], shp["x1"]))
    index0 = sorted(int(np.floor(v)) for v in (shp["y0"], shp["y1"]))
    return boxSelection((index0[0], index0[1]), (index1[0], index1[1]))


def selection_from_store(store: dict | None) -> Selection | None:
    """What the spectrum should be summed over: the submitted polygon, else
    the box, else nothing (the full map)."""
    submitted = submitted_polygon(store)
    if submitted is not None and len(submitted) >= MIN_POLYGON_POINTS:
        return polygonSelection(tuple((float(x), float(y)) for x, y in submitted))
    shapes = active_shapes(store)
    if shapes and shapes[0].get("type") == "rect":
        return box_from_shape(shapes[0])
    return None


def selection_key(store: dict | None) -> str:
    """A string that changes exactly when the selection does."""
    selection = selection_from_store(store)
    if selection is None:
        return "full"
    return f"{type(selection).__name__}:{json.dumps(asdict(selection), sort_keys=True)}"


def _path(points: list[Point]) -> str:
    moves = " L ".join(f"{x},{y}" for x, y in points)
    closed = " Z" if len(points) >= MIN_POLYGON_POINTS else ""
    return f"M {moves}{closed}"


def polygon_shapes(
    points: list[Point], radius: float = DEFAULT_VERTEX_RADIUS
) -> list[dict]:
    """The layout shapes drawing a polygon in progress: a line through the
    points (closed once there are three) and a circle of ``radius`` data
    units on each of them. None of it is editable; the points are changed by
    clicking."""
    shapes: list[dict] = []
    if len(points) >= 2:
        closed = len(points) >= MIN_POLYGON_POINTS
        shapes.append(
            {
                "type": "path",
                "path": _path(points),
                "xref": "x",
                "yref": "y",
                "line": {"color": POLYGON_COLOR, "width": 2},
                "fillcolor": POLYGON_FILL if closed else "rgba(0,0,0,0)",
                "editable": False,
                "name": POLYGON_KEY,
            }
        )
    shapes.extend(
        {
            "type": "circle",
            "xref": "x",
            "yref": "y",
            "x0": x - radius,
            "x1": x + radius,
            "y0": y - radius,
            "y1": y + radius,
            "line": {"color": VERTEX_OUTLINE, "width": 1},
            "fillcolor": POLYGON_COLOR,
            "editable": False,
            "name": f"{POLYGON_KEY}-vertex",
        }
        for x, y in points
    )
    return shapes


def add_point(points: list[Point], x: float, y: float) -> list[Point]:
    return [*points, [float(x), float(y)]]


def nearest_point(points: list[Point], x: float, y: float) -> tuple[int, float] | None:
    """The index of the point closest to ``(x, y)`` and its distance."""
    if not points:
        return None
    distances = [math.hypot(px - x, py - y) for px, py in points]
    index = int(np.argmin(distances))
    return index, distances[index]


def remove_nearest_point(
    points: list[Point], x: float, y: float, tolerance: float
) -> list[Point]:
    """The points without the one nearest ``(x, y)``, if that one lies within
    ``tolerance``; otherwise the points unchanged."""
    nearest = nearest_point(points, x, y)
    if nearest is None or nearest[1] > tolerance:
        return list(points)
    index = nearest[0]
    return [p for i, p in enumerate(points) if i != index]


def pick_tolerance(
    visible_spans: tuple[float, float], fraction: float = VERTEX_PICK_FRACTION
) -> float:
    """How far from a vertex a click may land and still pick it: a fraction
    of the larger visible extent, so it tracks the zoom."""
    return fraction * max(visible_spans)

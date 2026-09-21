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

# the polygon's look: the path and the corners in between are white, the
# corner the path starts at is green and the one it ends at (where a click
# appends the next) is red
POLYGON_COLOR = "#f8f9fa"
POLYGON_FILL = "rgba(248, 249, 250, 0.15)"
VERTEX_OUTLINE = "#212529"
START_VERTEX_COLOR = "#3fb950"
END_VERTEX_COLOR = "#f85149"

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
        """The half-open index ranges of the pixel rectangle around the
        polygon: from the pixel holding its lowest corner to the one holding
        its highest on each axis (pixel ``i`` spans ``i - 0.5`` to ``i +
        0.5``), clipped to the image when its shape is known. This is wider
        than the pixels the server sums, whose centres must fall inside."""
        verts = np.asarray(self.vertices, dtype=float)
        ranges: list[IndexRange] = []
        for axis in range(2):
            lo = math.floor(verts[:, axis].min() + 0.5)
            hi = math.floor(verts[:, axis].max() + 0.5) + 1
            if image_shape is not None:
                lo = min(max(lo, 0), image_shape[axis])
                hi = min(max(hi, lo), image_shape[axis])
            ranges.append((lo, max(hi, lo)))
        return ranges[0], ranges[1]

    def cropped_points(
        self, bounds: tuple[IndexRange, IndexRange] | None = None
    ) -> list[Point]:
        """The corners in the coordinates of the image cropped to ``bounds``
        (its origin moves to the crop's first pixel), or as they are."""
        offset0, offset1 = (0, 0) if bounds is None else (bounds[0][0], bounds[1][0])
        return [[x - offset1, y - offset0] for x, y in self.points]


Selection = boxSelection | polygonSelection

DEFAULT_OUTLINE_COLOR = "#ffffff"


@dataclass(frozen=True)
class outlineStyle:
    """How the exported figures draw the selection: whether at all, and the
    colours of the line and of a polygon's corner dots."""

    show: bool = True
    line_color: str = DEFAULT_OUTLINE_COLOR
    dot_color: str = DEFAULT_OUTLINE_COLOR


def overlay_shapes(
    selection: Selection,
    style: outlineStyle,
    image_shape: tuple[int, int],
    bounds: tuple[IndexRange, IndexRange] | None = None,
) -> list[dict]:
    """The layout shapes an exported figure draws for the selection over an
    image of ``image_shape`` (rows, columns): the pixel-aligned rectangle of
    a box, or a polygon's outline and a dot on each corner, in the crop's
    coordinates when ``bounds`` are given. Nothing when the style hides the
    outline, and nothing over a box's own crop, which is the box."""
    if not style.show:
        return []
    if isinstance(selection, boxSelection):
        if bounds is not None:
            return []
        (r0, r1), (c0, c1) = selection.index0_range, selection.index1_range
        return [
            {
                "type": "rect",
                "x0": c0 - 0.5,
                "x1": c1 - 0.5,
                "y0": r0 - 0.5,
                "y1": r1 - 0.5,
                "line": {"color": style.line_color, "width": 2},
                "fillcolor": "rgba(0,0,0,0)",
            }
        ]
    points = selection.cropped_points(bounds)
    spans = (float(image_shape[0]), float(image_shape[1]))
    radius = vertex_radius_for(spans)
    return [
        polygon_outline(points, color=style.line_color),
        *(
            vertex_shape(x, y, radius, style.dot_color, style.dot_color)
            for x, y in points
        ),
    ]


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


def polygon_outline(
    points: list[Point], fill: bool = False, color: str = POLYGON_COLOR
) -> dict:
    """The path shape through ``points``, closed once there are three, with
    the panels' translucent fill when ``fill`` is set and none otherwise."""
    closed = len(points) >= MIN_POLYGON_POINTS
    return {
        "type": "path",
        "path": _path(points),
        "xref": "x",
        "yref": "y",
        "line": {"color": color, "width": 2},
        "fillcolor": POLYGON_FILL if fill and closed else "rgba(0,0,0,0)",
        "editable": False,
        "name": POLYGON_KEY,
    }


def vertex_shape(
    x: float,
    y: float,
    radius: float,
    fill_color: str,
    line_color: str = VERTEX_OUTLINE,
) -> dict:
    """The circle of ``radius`` data units marking a corner at ``(x, y)``."""
    return {
        "type": "circle",
        "xref": "x",
        "yref": "y",
        "x0": x - radius,
        "x1": x + radius,
        "y0": y - radius,
        "y1": y + radius,
        "line": {"color": line_color, "width": 1},
        "fillcolor": fill_color,
        "editable": False,
        "name": f"{POLYGON_KEY}-vertex",
    }


def polygon_shapes(
    points: list[Point], radius: float = DEFAULT_VERTEX_RADIUS
) -> list[dict]:
    """The layout shapes drawing a polygon in progress: a line through the
    points (closed once there are three) and a circle of ``radius`` data
    units on each of them. None of it is editable; the points are changed by
    clicking."""
    shapes: list[dict] = []
    if len(points) >= 2:
        shapes.append(polygon_outline(points, fill=True))
    shapes.extend(
        vertex_shape(x, y, radius, vertex_color(i, len(points)))
        for i, (x, y) in enumerate(points)
    )
    return shapes


def vertex_color(index: int, n_points: int) -> str:
    """Green for the corner the path starts at, red for the one it ends at,
    white in between; a lone corner is the start."""
    if index == 0:
        return START_VERTEX_COLOR
    if index == n_points - 1:
        return END_VERTEX_COLOR
    return POLYGON_COLOR


def add_point(
    points: list[Point], x: float, y: float, tolerance: float = 0.0
) -> list[Point]:
    """The points with ``(x, y)`` appended, unless it lands within
    ``tolerance`` of an existing corner (a click on a corner is not a new
    one)."""
    nearest = nearest_point(points, x, y)
    if nearest is not None and nearest[1] <= tolerance:
        return list(points)
    return [*points, [float(x), float(y)]]


def move_point(points: list[Point], index: int, x: float, y: float) -> list[Point]:
    """The points with corner ``index`` moved to ``(x, y)``; an index that
    is not a corner leaves them unchanged."""
    if not 0 <= index < len(points):
        return list(points)
    moved = [list(p) for p in points]
    moved[index] = [float(x), float(y)]
    return moved


def nearest_segment(
    points: list[Point], x: float, y: float
) -> tuple[int, float] | None:
    """The segment of the closed polygon nearest ``(x, y)``: the index of
    the corner it starts at (the segment runs to the next corner, the last
    one closing back to the first) and the distance to it."""
    n = len(points)
    if n < 2:
        return None
    best: tuple[int, float] | None = None
    for i in range(n if n >= MIN_POLYGON_POINTS else n - 1):
        (ax, ay), (bx, by) = points[i], points[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            t = 0.0
        else:
            t = min(1.0, max(0.0, ((x - ax) * dx + (y - ay) * dy) / length_sq))
        distance = math.hypot(ax + t * dx - x, ay + t * dy - y)
        if best is None or distance < best[1]:
            best = (i, distance)
    return best


def insert_point_on_nearest_segment(
    points: list[Point], x: float, y: float, tolerance: float
) -> list[Point]:
    """The points with ``(x, y)`` inserted as a corner of the segment nearest
    to it, when that segment lies within ``tolerance``; otherwise the points
    unchanged."""
    nearest = nearest_segment(points, x, y)
    if nearest is None or nearest[1] > tolerance:
        return list(points)
    index = nearest[0] + 1
    return [*points[:index], [float(x), float(y)], *points[index:]]


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

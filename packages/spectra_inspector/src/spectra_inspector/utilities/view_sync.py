"""Keep several image panels showing the same view.

Plotly reports zooms, pans, tool changes and shape edits through a graph's
``relayoutData`` as flattened property paths (``"xaxis.range[0]"``,
``"shapes[0].x1"``, ...). The graph's ``figure`` prop does *not* pick up the
resulting axis ranges, so the shared view has to be rebuilt from those events.
It lives in a small dict (see ``empty_view``) kept in a ``dcc.Store`` and is
applied to every panel, either as a ``Patch`` on an existing figure or directly
on a freshly built one.
"""

import re
from typing import Any

from dash import Patch
from plotly.graph_objects import Figure

AXES = ("xaxis", "yaxis")

# what px.imshow sets, so a reset returns to the un-zoomed image rather than to
# plotly's generic default (which would flip the y axis).
DEFAULT_AUTORANGE: dict[str, bool | str] = {"xaxis": True, "yaxis": "reversed"}

_RANGE_INDEX = re.compile(r"^([xy]axis)\.range\[([01])\]$")
_SHAPE_ATTR = re.compile(r"^shapes\[(\d+)\]\.(\w+)$")


def empty_view() -> dict[str, Any]:
    """A view that leaves every panel at its own defaults.

    Each axis entry is either ``None`` (default, auto-ranged) or
    ``{"range": [r0, r1]}`` in plotly's (possibly reversed) order.
    """
    return {"dragmode": None, "xaxis": None, "yaxis": None}


def ensure_view(view: dict[str, Any] | None) -> dict[str, Any]:
    full = empty_view()
    if view:
        full.update({k: v for k, v in view.items() if k in full})
    return full


def update_view_from_relayout(
    view: dict[str, Any], relay: dict[str, Any]
) -> tuple[dict[str, Any], bool, bool]:
    """Fold one relayoutData event into a view.

    Returns the new view and whether the axes and the dragmode changed. Keys
    that do not describe the view (``autosize``, selections, shapes, ...) are
    ignored.
    """
    new_view = ensure_view(view)
    axes_changed = False
    dragmode_changed = False

    if "dragmode" in relay and relay["dragmode"] != new_view["dragmode"]:
        new_view["dragmode"] = relay["dragmode"]
        dragmode_changed = True

    for ax in AXES:
        new_axis = _axis_from_relayout(ax, relay, new_view[ax])
        if new_axis != new_view[ax]:
            new_view[ax] = new_axis
            axes_changed = True

    return new_view, axes_changed, dragmode_changed


def _axis_from_relayout(
    ax: str, relay: dict[str, Any], current: dict[str, Any] | None
) -> dict[str, Any] | None:
    # a double click (or a modebar reset) reports autorange for the axes that
    # had none set and an explicit range for the others. Either way the axis is
    # back at its default, which is what None means here.
    if relay.get(f"{ax}.autorange"):
        return None

    if f"{ax}.range" in relay:
        return {"range": [float(v) for v in relay[f"{ax}.range"]]}

    partial: dict[int, float] = {}
    for key, value in relay.items():
        match = _RANGE_INDEX.match(key)
        if match and match.group(1) == ax:
            partial[int(match.group(2))] = float(value)
    if not partial:
        return current

    if len(partial) == 2:
        return {"range": [partial[0], partial[1]]}

    # only one end moved: keep the other end from the view we already have
    if current is not None and "range" in current:
        rng = list(current["range"])
        for idx, value in partial.items():
            rng[idx] = value
        return {"range": rng}
    return current


def shapes_from_relayout(
    relay: dict[str, Any], current_shapes: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool]:
    """The active shapes after one relayoutData event.

    Drawing a shape reports the full ``shapes`` list, of which only the latest
    is kept: a single box drives the spectrum. Dragging an existing shape
    reports ``shapes[i].<attr>`` keys, which are applied to the kept shape.
    """
    if "shapes" in relay:
        shapes = list(relay["shapes"] or [])
        if len(shapes) > 1:
            shapes = shapes[-1:]
        return shapes, shapes != current_shapes

    shapes = [dict(shp) for shp in current_shapes]
    changed = False
    for key, value in relay.items():
        match = _SHAPE_ATTR.match(key)
        if match is None:
            continue
        idx = int(match.group(1))
        if idx < len(shapes):
            shapes[idx][match.group(2)] = value
            changed = True
    return shapes, changed


def sorted_axis_range(view: dict[str, Any], ax: str) -> list[float] | None:
    """The view's range for an axis in ascending order, None when default."""
    axis = ensure_view(view)[ax]
    if axis is None or "range" not in axis:
        return None
    return sorted(float(v) for v in axis["range"])


def apply_view_to_figure(
    fig: Figure,
    view: dict[str, Any] | None,
    shapes: list[dict[str, Any]] | None = None,
) -> Figure:
    """Put a freshly built figure into the shared view."""
    view = ensure_view(view)
    for ax in AXES:
        axis = view[ax]
        if axis is None:
            fig.update_layout({ax: {"range": None, "autorange": DEFAULT_AUTORANGE[ax]}})
        else:
            fig.update_layout({ax: {"range": list(axis["range"]), "autorange": False}})
    if view["dragmode"] is not None:
        fig.update_layout(dragmode=view["dragmode"])
    if shapes is not None:
        fig.update_layout(shapes=shapes)
    return fig


def apply_axes_to_patch(patch: Patch, view: dict[str, Any]) -> Patch:
    """Add the view's axis ranges to a figure Patch."""
    view = ensure_view(view)
    for ax in AXES:
        axis = view[ax]
        if axis is None:
            patch["layout"][ax]["autorange"] = DEFAULT_AUTORANGE[ax]
            del patch["layout"][ax]["range"]
        else:
            patch["layout"][ax]["range"] = list(axis["range"])
            patch["layout"][ax]["autorange"] = False
    return patch

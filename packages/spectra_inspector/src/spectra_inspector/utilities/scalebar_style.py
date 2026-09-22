"""How the exported figures draw the scalebar, and how a scalebar is told
apart from everything else on an image figure."""

from dataclasses import dataclass
from typing import Any

# the tags the scalebar's trace and label carry, so the export can find them
# among the selection's shapes and anything else drawn on the figure
SCALEBAR_META_KEY = "scalebar"
SCALEBAR_ANNOTATION_NAME = "scalebar"

DEFAULT_SCALEBAR_COLOR = "#ffffff"
DEFAULT_SCALEBAR_FONTSIZE = 10


@dataclass(frozen=True)
class scalebarStyle:
    """How the exported figures draw the scalebar: whether at all, and the
    colour and label size (in points)."""

    show: bool = True
    color: str = DEFAULT_SCALEBAR_COLOR
    fontsize: int = DEFAULT_SCALEBAR_FONTSIZE


def is_scalebar_trace(trace: dict[str, Any]) -> bool:
    meta = trace.get("meta")
    return isinstance(meta, dict) and bool(meta.get(SCALEBAR_META_KEY))


def is_scalebar_annotation(annotation: dict[str, Any]) -> bool:
    return annotation.get("name") == SCALEBAR_ANNOTATION_NAME


def scalebar_styled(figure: dict[str, Any], style: scalebarStyle) -> dict[str, Any]:
    """A copy of a figure dict with its scalebar drawn as ``style`` says: the
    bar and label in the style's colour, the label at its size, or both
    removed when the style hides them. A figure without a scalebar is
    returned as it is."""
    data = list(figure.get("data") or [])
    layout = dict(figure.get("layout") or {})
    annotations = list(layout.get("annotations") or [])

    if not style.show:
        data = [trace for trace in data if not is_scalebar_trace(trace)]
        annotations = [a for a in annotations if not is_scalebar_annotation(a)]
    else:
        data = [
            (
                {**trace, "line": {**(trace.get("line") or {}), "color": style.color}}
                if is_scalebar_trace(trace)
                else trace
            )
            for trace in data
        ]
        annotations = [
            (
                {
                    **a,
                    "font": {
                        **(a.get("font") or {}),
                        "color": style.color,
                        "size": style.fontsize,
                    },
                }
                if is_scalebar_annotation(a)
                else a
            )
            for a in annotations
        ]
    return {**figure, "data": data, "layout": {**layout, "annotations": annotations}}

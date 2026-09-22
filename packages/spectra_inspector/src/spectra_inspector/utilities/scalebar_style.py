"""How the image panels and the exported figures draw the scalebar, and how a
scalebar is told apart from everything else on an image figure."""

import re
from dataclasses import asdict, dataclass
from typing import Any

# the tags the scalebar's trace and label carry, so the export can find them
# among the selection's shapes and anything else drawn on the figure
SCALEBAR_META_KEY = "scalebar"
SCALEBAR_ANNOTATION_NAME = "scalebar"

DEFAULT_SCALEBAR_COLOR = "#f32a2a"
DEFAULT_SCALEBAR_FONTSIZE = 16
# the label sizes (points) the text-size input accepts
MIN_SCALEBAR_FONTSIZE = 4
MAX_SCALEBAR_FONTSIZE = 40

# what a native colour input reports
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass(frozen=True)
class scalebarStyle:
    """How the scalebar is drawn: whether at all, and the colour and label
    size (in points) of the bar and its label."""

    show: bool = True
    color: str = DEFAULT_SCALEBAR_COLOR
    fontsize: int = DEFAULT_SCALEBAR_FONTSIZE

    def to_store(self) -> dict[str, Any]:
        return asdict(self)


def scalebar_style(
    include: bool | None,
    color: str | None,
    fontsize: float | str | None,
) -> scalebarStyle:
    """The style the toolbox's scalebar controls give: an unset control or a
    value that is not a ``#rrggbb`` colour or a size within the input's range
    means its default."""
    size = DEFAULT_SCALEBAR_FONTSIZE
    try:
        candidate = round(float(fontsize))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        candidate = None
    if (
        candidate is not None
        and MIN_SCALEBAR_FONTSIZE <= candidate <= MAX_SCALEBAR_FONTSIZE
    ):
        size = candidate
    return scalebarStyle(
        show=True if include is None else bool(include),
        color=(
            color if color and _HEX_COLOR.fullmatch(color) else DEFAULT_SCALEBAR_COLOR
        ),
        fontsize=size,
    )


def scalebar_style_from_store(data: dict[str, Any] | None) -> scalebarStyle:
    """The style held in the page's scalebar store (``scalebarStyle.to_store``),
    the default for an empty or malformed one."""
    data = data or {}
    return scalebar_style(data.get("show"), data.get("color"), data.get("fontsize"))


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
                {
                    **trace,
                    "visible": True,
                    "line": {**(trace.get("line") or {}), "color": style.color},
                }
                if is_scalebar_trace(trace)
                else trace
            )
            for trace in data
        ]
        annotations = [
            (
                {
                    **a,
                    "visible": True,
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

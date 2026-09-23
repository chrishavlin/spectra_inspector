import matplotlib as mpl
import matplotlib.pyplot as mpl_pyplot  # noqa: ICN001
from matplotlib.colors import to_rgb
from matplotlib.font_manager import FontProperties
from matplotlib.offsetbox import AnchoredOffsetbox, AuxTransformBox, TextArea, VPacker
from matplotlib.patches import Circle, Polygon, Rectangle
from matplotlib.patheffects import withStroke

mpl.use("Agg")

__all__ = [
    "AnchoredOffsetbox",
    "AuxTransformBox",
    "Circle",
    "FontProperties",
    "Polygon",
    "Rectangle",
    "TextArea",
    "VPacker",
    "mpl",
    "mpl_pyplot",
    "to_rgb",
    "withStroke",
]

import math
import zlib
from dataclasses import dataclass

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.degrees import Latitude, Longitude
from spectra_inspector.utilities.model import AvailableDatasets

# plotly's built-in "satellite" style hides its ESRI layer from zoom 16 on
# (the style was written for Catalonia, where another source takes over), so
# the imagery is declared here instead. The source's `maxzoom` is the deepest
# tile level requested: ESRI answers deeper requests over remote terrain with
# a "map data not yet available" tile, and stopping short of that makes
# maplibre stretch the last real tiles instead.
_SATELLITE_STYLE = {
    "version": 8,
    "id": "esri-world-imagery",
    "sources": {
        "esri-world-imagery": {
            "type": "raster",
            "tiles": [
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ],
            "tileSize": 256,
            "maxzoom": 17,
            "attribution": "ESRI &copy; <a href='http://www.esri.com'>ESRI</a>",
        }
    },
    "layers": [
        {"id": "esri-world-imagery", "type": "raster", "source": "esri-world-imagery"}
    ],
}

_map_styles = {
    "OpenStreetMap": "open-street-map",
    "Satellite": _SATELLITE_STYLE,
    "Satellite-Composite": "satellite-streets",
    "None": "white-bg",
}


# the figure's traces: a disc under the active sample's point, then the samples
RING_TRACE = 0
SAMPLE_TRACE = 1

MAP_HEIGHT = "30rem"

# the map's size in pixels as `select_zoom` assumes it. The height is
# MAP_HEIGHT; the width follows the page and is not known here, so the view
# it computes is approximate across the map.
_VIEW_PX = (800, 480)
# maplibre draws the world 512 pixels wide at zoom 0
_WORLD_PX = 512
# the deepest zoom a click goes to, short of where the imagery ends
MAX_SELECT_ZOOM = 16.0
# zoom levels `extent_view` stays back from an exact fit, which keeps the
# outermost samples off the edge of the map
_EXTENT_MARGIN = 0.4

_SAMPLE_COLOR = "blue"
_RING_COLOR = "orange"
# a sample the table has filtered out: the sample color mixed with white.
# Opaque, because points stacked on one spot add their opacities up and a
# faded stack looks like a full one.
_DIMMED_COLOR = "#a6a6ff"

# samples closer than this in both latitude and longitude (degrees, about a
# metre) are drawn on top of each other and cannot be told apart by a click
COLOCATED_DELTA = 1e-5

# marker diameter in pixels by the number of maps at a point: (at least, size)
_SIZE_STEPS = ((4, 32), (2, 26), (0, 20))

# the hover lines that are merged over the samples stacked on a point
_STACKED_HOVER_COLS = (
    "group_name",
    "sample_type",
    "description",
    "longitude",
    "latitude",
    "elevation",
)
# how a stack's merged hover line shows a sample without a value
_MISSING = "-"
# the hover title as px writes it for `hover_name`
_PX_HOVER_TITLE = "<b>%{hovertext}</b><br><br>"


@dataclass
class mapSettings:
    center_lat: float = -50.953878
    center_lon: float = -72.983542
    dlat: float = 5.0
    dlon: float = 5.0
    gridwid_lon: float = 0.1
    gridwid_lat: float = 0.1
    ticks_lon: float = 1.0
    ticks_lat: float = 1.0
    placename: str = "Torres del Paine"
    init_zoom_level: float = 10
    elevation_m: float = 180

    @property
    def min_lon(self):
        return self.validate_lon(self.center_lon - self.dlon / 2)

    @property
    def max_lon(self):
        return self.validate_lon(self.center_lon + self.dlon / 2)

    @property
    def min_lat(self):
        return self.validate_lat(self.center_lat - self.dlat / 2)

    @property
    def max_lat(self):
        return self.validate_lat(self.center_lat + self.dlat / 2)

    @property
    def lon_range(self):
        return self.min_lon, self.max_lon

    @property
    def lat_range(self):
        return self.min_lat, self.max_lat

    @staticmethod
    def validate_lon(lon):
        if lon > 360:
            return lon - 360
        return lon

    @staticmethod
    def validate_lat(lat):
        if lat < -89.9:
            return -89.9
        if lat > 89.9:
            return 89.9
        return lat


class sampleMapLayoutIDs(indexedLayoutIDMapper):
    prop_names: tuple[str, ...] = (
        "div",
        "samplemap",
        "dropdown",
        "focus",
        "extent",
    )

    def __init__(self, id_type_base: str = "sample-map", index: int | None = None):
        super().__init__(id_type_base, index)

    @property
    def samplemap(self) -> str:
        return self.full_id("-samplemap")

    @property
    def dropdown(self) -> str:
        return self.full_id("-dropdown")

    @property
    def focus(self) -> str:
        return self.full_id("-focus")

    @property
    def extent(self) -> str:
        return self.full_id("-extent")


def _default_center(df: pd.DataFrame | None) -> dict[str, float]:
    """Mean of the finite lat/lon values, falling back to the mapSettings default."""
    ms = mapSettings()
    center = {"lat": ms.center_lat, "lon": ms.center_lon}
    if df is None:
        return center
    for key in ("lat", "lon"):
        if key in df:
            mean_val = pd.to_numeric(df[key], errors="coerce").mean()
            if pd.notna(mean_val):
                center[key] = float(mean_val)
    return center


def _marker_size(n_maps: int) -> int:
    return next(size for at_least, size in _SIZE_STEPS if n_maps >= at_least)


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _spot_summary(
    df: pd.DataFrame, map_samples: dict[str, str] | None
) -> tuple[list[str], list[int], list[list[int]]]:
    """For each sample, what shares its point on the map: a hover line naming
    the samples stacked there and counting their maps, that count, and the
    rows of those samples. The stacking is `colocated_sample_ids`'s: a sample
    without a location stands alone. A stack is listed in the order of the
    rows, so that every point of it reads the same."""
    ids = df["sample_id"].astype(str).to_numpy()
    lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)
    maps_of: dict[str, int] = {}
    for sample_id in (map_samples or {}).values():
        maps_of[str(sample_id)] = maps_of.get(str(sample_id), 0) + 1

    lines, counts, stacks = [], [], []
    for i in range(len(ids)):
        near = (np.abs(lat - lat[i]) <= COLOCATED_DELTA) & (
            np.abs(lon - lon[i]) <= COLOCATED_DELTA
        )
        near[i] = True
        rows = np.flatnonzero(near).tolist()
        here = list(dict.fromkeys(ids[rows]))
        n_maps = sum(maps_of.get(s, 0) for s in here)
        line = _plural(n_maps, "map")
        if len(here) > 1:
            line = f"{len(here)} samples ({', '.join(here)}), {line}"
        lines.append(line)
        counts.append(n_maps)
        stacks.append(rows)
    return lines, counts, stacks


def _unified(values: list) -> object:
    """One hover value for a stack of samples: the value they share, or all
    of theirs in the order of the stack."""
    shown = [_MISSING if pd.isna(v) else v for v in values]
    if len(set(shown)) == 1:
        return values[0]
    return ", ".join(map(str, shown))


def _unify_stacks(df: pd.DataFrame, stacks: list[list[int]]) -> list[str]:
    """Make the hover of stacked samples describe the stack, in place: only
    the topmost point of a stack can be hovered, so each of its points carries
    every sample's values. Returns the hover titles, the sample id for a
    sample alone on its point and nothing for a stack, whose samples the
    "at this point" line names."""
    for col in _STACKED_HOVER_COLS:
        values = df[col].tolist()
        df[col] = pd.Series(
            [_unified([values[j] for j in rows]) for rows in stacks],
            index=df.index,
            dtype=object,
        )
    return [
        f"<b>{sample_id}</b><br><br>" if len(rows) == 1 else ""
        for sample_id, rows in zip(df["sample_id"], stacks, strict=True)
    ]


def get_map(
    map_style: str | dict, available_data: AvailableDatasets | None = None
) -> go.Figure:

    ms = mapSettings()

    records = []
    map_samples = None
    if available_data is not None and available_data.sample_metadata is not None:
        records = available_data.sample_metadata.records or []
        map_samples = available_data.sample_metadata.map_samples

    if not records:
        recs = [
            {
                "lat": ms.center_lat,
                "lon": ms.center_lon,
                "name": ms.placename,
                "elevation": ms.elevation_m,
                "marker_size": 20,
                "sample_id": "0",
                "group_name": "0",
            },
        ]
        df = pd.DataFrame(recs)
        center = _default_center(None)
        hd_cols = ["group_name", "lat", "lon", "elevation"]
        sizes = None
        titles = None

    else:
        df = pd.DataFrame([record.model_dump() for record in records])
        df["marker_size"] = 10

        def _attach_better_latlon(row):

            if not pd.isna(row["lat"]):
                lat = Latitude(row["lat"], cardinal_str="N")
                row["latitude"] = lat.to_str()

            if not pd.isna(row["lon"]):
                lon = Longitude(row["lon"], cardinal_str="E")
                row["longitude"] = lon.to_str()

            return row

        df["latitude"] = ""
        df["longitude"] = ""

        df = df.apply(_attach_better_latlon, axis=1)
        df["here"], n_maps, stacks = _spot_summary(df, map_samples)
        sizes = [_marker_size(n) for n in n_maps]
        titles = _unify_stacks(df, stacks)

        hd_cols = {
            "here": True,
            "group_name": True,
            "sample_type": True,
            "description": True,
            "lat": False,
            "lon": False,
            "longitude": True,
            "latitude": True,
            "elevation": True,
            "marker_size": False,
        }

        center = _default_center(df)

    # https://plotly.github.io/plotly.py-docs/generated/plotly.express.scatter_map.html
    fig = px.scatter_map(
        df,
        lat="lat",
        lon="lon",
        hover_name="sample_id",
        hover_data=hd_cols,
        map_style=map_style,
        size="marker_size",
        opacity=1.0,
        labels={"here": "at this point"},
    )
    if sizes is not None:
        # a point grows with the number of maps on it, so a stack of samples
        # or a sample mapped several times stands out
        fig.update_traces(marker={"size": sizes, "sizemode": "diameter", "sizeref": 1})
    if titles is not None:
        # the title carries its own markup, so that a stack has no title at
        # all rather than an empty one
        fig.update_traces(
            hovertext=titles,
            hovertemplate=fig.data[0].hovertemplate.replace(
                _PX_HOVER_TITLE, "%{hovertext}"
            ),
        )
    fig.update_layout(
        autosize=True,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
    )
    # `selectedpoints` is what dims the samples the table has filtered out
    # (`point_styling`), and what plotly's own box and lasso tools set, so a
    # selected point looks like an ordinary one and an unselected one pales.
    fig.update_traces(
        marker_color=_SAMPLE_COLOR,
        selected={"marker": {"color": _SAMPLE_COLOR, "opacity": 1.0}},
        unselected={"marker": {"color": _DIMMED_COLOR, "opacity": 1.0}},
    )

    # too low res, but shows how to use the map_layers arg
    # USGS_mapservers = {
    #     'relief': "https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}",
    #     'satellite': "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",

    # }
    # map_layers=[
    #         {
    #             "below": 'traces',
    #             "sourcetype": "raster",
    #             "sourceattribution": "United States Geological Survey",
    #             "source": [USGS_mapservers['relief']]
    #         }
    #     ],

    map_dict = {
        "bearing": 0,
        "center": go.layout.map.Center(**center),
        "pitch": 0,
        "zoom": ms.init_zoom_level,
    }

    fig.update_layout(
        hovermode="closest",
        # map_style="white-bg",
        # map_layers=map_layers,
        map=map_dict,
    )

    # px stores the hover_data columns in `customdata` and references them
    # from `hovertemplate` by index, so the sample ids are appended as an
    # extra trailing column rather than replacing the array.
    sample_ids = df["sample_id"].astype(str).to_numpy(dtype=object)

    for trace in fig.data:
        n_pts = len(trace.lat) if trace.lat is not None else 0
        ids = sample_ids[:n_pts, np.newaxis]
        if trace.customdata is None:
            trace.customdata = ids
        else:
            existing = np.asarray(trace.customdata, dtype=object)
            trace.customdata = np.column_stack([existing, ids])

    # scattermap markers have no outline, so the active sample is marked by a
    # larger disc drawn underneath its point. It sits first in the trace list
    # to stay below the samples and out of the way of their hover and clicks.
    fig.add_trace(
        go.Scattermap(
            lat=[],
            lon=[],
            mode="markers",
            marker={"size": 40, "color": _RING_COLOR, "opacity": 0.9},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.data = (fig.data[-1], *fig.data[:-1])
    # The revision keeps the zoom and pan the user has set when the page swaps
    # in a restyled figure, which would otherwise snap the view back to the
    # figure's own. A center that differs from the previous figure's still
    # applies, which is how selecting a dataset moves the map. It is derived
    # from the samples, so a figure for another listing starts from its own
    # view.
    revision = zlib.crc32("\n".join(map(str, sample_ids)).encode())
    fig.update_layout(showlegend=False, uirevision=f"samples-{revision}")

    return fig


def _sample_id_from_customdata(point_data) -> str | None:
    """Return the sample id stored as the last `customdata` column for a point."""
    if isinstance(point_data, (list, tuple, np.ndarray)):
        if len(point_data) == 0:
            return None
        return str(point_data[-1])
    return str(point_data)


def sample_ids_from_points(event_data: dict | None) -> list[str]:
    """The sample ids of the points in a `clickData` or `selectedData` payload,
    in the order given and without repeats."""
    ids: list[str] = []
    for point in (event_data or {}).get("points") or []:
        if point.get("curveNumber", SAMPLE_TRACE) != SAMPLE_TRACE:
            continue
        custom = point.get("customdata")
        if custom is None:
            continue
        sample_id = _sample_id_from_customdata(custom)
        if sample_id is not None and sample_id not in ids:
            ids.append(sample_id)
    return ids


def _location(record: dict) -> tuple[float, float] | None:
    lat = pd.to_numeric(record.get("lat"), errors="coerce")
    lon = pd.to_numeric(record.get("lon"), errors="coerce")
    if pd.isna(lat) or pd.isna(lon):
        return None
    return float(lat), float(lon)


def colocated_sample_ids(
    records: list[dict] | None,
    sample_ids: list[str],
    delta: float = COLOCATED_DELTA,
) -> list[str]:
    """The given samples followed by the ones sharing a location with any of
    them. A click reports only the topmost of a stack of points, so this is
    what the click could have meant."""
    records = records or []
    wanted = set(sample_ids)
    spots = [
        spot
        for r in records
        if str(r["sample_id"]) in wanted and (spot := _location(r)) is not None
    ]
    ids = list(sample_ids)
    for record in records:
        sample_id = str(record["sample_id"])
        spot = _location(record)
        if sample_id in ids or spot is None:
            continue
        if any(
            abs(spot[0] - lat) <= delta and abs(spot[1] - lon) <= delta
            for lat, lon in spots
        ):
            ids.append(sample_id)
    return ids


def sample_location(
    records: list[dict] | None, sample_id: str | None
) -> dict[str, float] | None:
    """Where a sample is, as a map center; None if it has no location."""
    if sample_id is None:
        return None
    for record in records or []:
        if str(record["sample_id"]) == str(sample_id):
            spot = _location(record)
            return None if spot is None else {"lat": spot[0], "lon": spot[1]}
    return None


def _mercator_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def select_zoom(
    records: list[dict] | None, percent: float, center: dict[str, float]
) -> float | None:
    """The zoom at which the map, centered on ``center``, spans ``percent`` of
    the extent of all the located samples: of their longitudes across and of
    their latitudes down, whichever needs the wider view. None when there is
    nothing to derive it from: a percentage of 0, or samples all in one spot.
    """
    spots = [spot for r in records or [] if (spot := _location(r)) is not None]
    if percent <= 0 or not spots:
        return None
    share = percent / 100
    lats, lons = zip(*spots, strict=True)
    dlon = (max(lons) - min(lons)) * share
    dlat = (max(lats) - min(lats)) * share

    zooms = []
    if dlon > 0:
        zooms.append(math.log2(_VIEW_PX[0] * 360 / (_WORLD_PX * dlon)))
    if dlat > 0:
        lat = center["lat"]
        south = max(lat - dlat / 2, -85.0)
        north = min(lat + dlat / 2, 85.0)
        dy = _mercator_y(north) - _mercator_y(south)
        if dy > 0:
            zooms.append(math.log2(_VIEW_PX[1] * 2 * math.pi / (_WORLD_PX * dy)))
    if not zooms:
        return None
    return min(max(min(zooms), 0.0), MAX_SELECT_ZOOM)


def extent_view(records: list[dict] | None) -> tuple[dict[str, float], float] | None:
    """The center and zoom that show every located sample: the middle of
    their extent, which unlike their mean leaves none of them outside. None
    when no sample has a location."""
    spots = [spot for r in records or [] if (spot := _location(r)) is not None]
    if not spots:
        return None
    lats, lons = zip(*spots, strict=True)
    center = {
        "lat": (min(lats) + max(lats)) / 2,
        "lon": (min(lons) + max(lons)) / 2,
    }
    zoom = select_zoom(records, 100, center)
    if zoom is None:
        return center, mapSettings().init_zoom_level
    return center, max(zoom - _EXTENT_MARGIN, 0.0)


def _shares_a_spot(records: list[dict], of: np.ndarray) -> np.ndarray:
    """Which records lie within `COLOCATED_DELTA` of a record flagged in
    ``of``. A record without a location shares no spot."""
    lat, lon = (
        pd.to_numeric(
            pd.Series([r.get(key) for r in records], dtype=object), errors="coerce"
        ).to_numpy(dtype=float)
        for key in ("lat", "lon")
    )
    near = (np.abs(lat[:, np.newaxis] - lat[of]) <= COLOCATED_DELTA) & (
        np.abs(lon[:, np.newaxis] - lon[of]) <= COLOCATED_DELTA
    )
    return near.any(axis=1)


def point_styling(
    records: list[dict] | None,
    visible_samples: set[str] | None = None,
    active_sample: str | None = None,
) -> dict:
    """How the map should show a state of the dataset table.

    ``records`` are the sample sheet records the figure was built from, in the
    same order, which is what makes a point's index computable here.
    ``visible_samples`` are the samples with a row left in the table, None for
    "no filter"; ``active_sample`` is the sample of the selected dataset.

    Returns ``selectedpoints`` for the sample trace (None while every sample is
    visible, so nothing is dimmed), the coordinates of the active sample's
    disc (empty lists without one) and, when the active sample has a location,
    where to center the map. A sample stacked on a visible one counts as
    visible: the points cover each other, and a dimmed one on top would hide
    that the spot still has rows in the table.
    """
    records = records or []

    selectedpoints: list[int] | None = None
    if visible_samples is not None:
        visible = np.array(
            [str(r["sample_id"]) in visible_samples for r in records], dtype=bool
        )
        if not visible.all():
            shown = visible | _shares_a_spot(records, visible)
            selectedpoints = np.flatnonzero(shown).tolist()

    ring: dict[str, list[float]] = {"lat": [], "lon": []}
    center: dict[str, float] | None = None
    if active_sample is not None:
        for record in records:
            if str(record["sample_id"]) != str(active_sample):
                continue
            lat = pd.to_numeric(record.get("lat"), errors="coerce")
            lon = pd.to_numeric(record.get("lon"), errors="coerce")
            if pd.notna(lat) and pd.notna(lon):
                center = {"lat": float(lat), "lon": float(lon)}
                ring = {"lat": [center["lat"]], "lon": [center["lon"]]}
            break

    return {"selectedpoints": selectedpoints, "ring": ring, "center": center}


def apply_point_styling(fig: go.Figure, styling: dict) -> go.Figure:
    """Write a `point_styling` result into a figure. Without an active sample
    to center on, the figure keeps the center `get_map` gave it."""
    fig.data[SAMPLE_TRACE].selectedpoints = styling["selectedpoints"]
    fig.data[RING_TRACE].lat = styling["ring"]["lat"]
    fig.data[RING_TRACE].lon = styling["ring"]["lon"]
    if styling["center"] is not None:
        fig.update_layout(map_center=styling["center"])
    return fig


def get_layout(
    id_type_base: str = "sample-map",
    index: int = 0,
    available_data: None | AvailableDatasets = None,
) -> tuple[dbc.Container, sampleMapLayoutIDs]:

    IDS = sampleMapLayoutIDs(id_type_base=id_type_base, index=index)

    default_style = _map_styles["Satellite"]

    fig = get_map(default_style, available_data=available_data)

    OK_styles = list(_map_styles.keys())
    OK_styles.sort()

    map_style = dcc.Dropdown(
        OK_styles,
        value="Satellite",
        id=IDS.get_id_with_index("dropdown"),
        className="text-info",
        searchable=False,
        clearable=False,
    )

    layout = dbc.Container(
        [
            # what the page last moved the map to: a clicked sample or the
            # extent of all of them
            dcc.Store(id=IDS.get_id_with_index("focus")),
            dbc.Row(
                [
                    dbc.Col(map_style, width=4),
                    dbc.Col(
                        dbc.Button(
                            [html.I(className="fa fa-expand"), " Full Dataset"],
                            id=IDS.get_id_with_index("extent"),
                            color="secondary",
                            outline=True,
                            size="sm",
                        ),
                        width="auto",
                    ),
                ],
                className="g-2 align-items-center",
            ),
            dbc.Row(
                dbc.Col(
                    dcc.Graph(
                        figure=fig,
                        id=IDS.get_id_with_index("samplemap"),
                        config={"displaylogo": False},
                        # assets/dataset_table.js watches it for clicks that
                        # hit no sample
                        className="si-sample-map",
                        # a fixed height, so the map takes whatever width
                        # its column has without growing taller with it
                        style={"height": MAP_HEIGHT, "width": "100%"},
                    ),
                    width=12,
                )
            ),
        ]
    )
    return layout, IDS

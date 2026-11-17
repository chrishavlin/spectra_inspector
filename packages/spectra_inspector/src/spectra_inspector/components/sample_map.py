import zlib
from dataclasses import dataclass

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.utilities.degrees import Latitude, Longitude
from spectra_inspector.utilities.model import AvailableDatasets

_map_styles = {
    "OpenStreetMap": "open-street-map",
    "Satellite": "satellite",
    "Satellite-Composite": "satellite-streets",
    "None": "white-bg",
}


# the figure's traces: a disc under the active sample's point, then the samples
RING_TRACE = 0
SAMPLE_TRACE = 1

MAP_HEIGHT = "30rem"

_SAMPLE_COLOR = "blue"
_RING_COLOR = "orange"
_DIMMED_OPACITY = 0.25


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
    )

    def __init__(self, id_type_base: str = "sample-map", index: int | None = None):
        super().__init__(id_type_base, index)

    @property
    def samplemap(self) -> str:
        return self.full_id("-samplemap")

    @property
    def dropdown(self) -> str:
        return self.full_id("-dropdown")


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


def get_map(
    map_style: str, available_data: AvailableDatasets | None = None
) -> go.Figure:

    ms = mapSettings()

    records = []
    if available_data is not None and available_data.sample_metadata is not None:
        records = available_data.sample_metadata.records or []

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

        hd_cols = {
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
    )
    fig.update_layout(
        autosize=True,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
    )
    # `selectedpoints` is what dims the samples the table has filtered out
    # (`point_styling`), and what plotly's own box and lasso tools set, so a
    # selected point looks like an ordinary one and an unselected one fades.
    fig.update_traces(
        marker_color=_SAMPLE_COLOR,
        selected={"marker": {"color": _SAMPLE_COLOR, "opacity": 1.0}},
        unselected={"marker": {"color": _SAMPLE_COLOR, "opacity": _DIMMED_OPACITY}},
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
    # applies, which is how selecting a dataset moves the map. It is derived from the samples, so a figure for another
    # listing starts from its own view.
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
    where to center the map.
    """
    records = records or []

    selectedpoints: list[int] | None = None
    if visible_samples is not None:
        shown = [
            i for i, r in enumerate(records) if str(r["sample_id"]) in visible_samples
        ]
        if len(shown) < len(records):
            selectedpoints = shown

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
            dbc.Row(
                [
                    dbc.Col(map_style, width=4),
                ]
            ),
            dbc.Row(
                dbc.Col(
                    dcc.Graph(
                        figure=fig,
                        id=IDS.get_id_with_index("samplemap"),
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

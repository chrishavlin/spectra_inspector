from dataclasses import dataclass

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
from spectra_inspector.logging import spectraLogger
from spectra_inspector.utilities.degrees import Latitude, Longitude
from spectra_inspector.utilities.model import AvailableDatasets

_map_styles = {
    "OpenStreetMap": "open-street-map",
    "Satellite": "satellite",
    "Satellite-Composite": "satellite-streets",
    "None": "white-bg",
}


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


def get_map(
    map_style: str, available_data: AvailableDatasets | None = None
) -> go.Figure:

    ms = mapSettings()

    if available_data is None or available_data.sample_metadata is None:
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
        hd_cols = ["group_name", "lat", "lon", "elevation"]

    else:
        df = pd.DataFrame(available_data.sample_metadata["records"])
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
    )
    fig.update_traces(
        marker_color="blue",
        selected={"marker": {"color": "orange", "opacity": 1.0}},
        unselected={"marker": {"color": "blue", "opacity": 1.0}},
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
        "center": go.layout.map.Center(
            lat=ms.center_lat,
            lon=ms.center_lon,
        ),
        "pitch": 0,
        "zoom": ms.init_zoom_level,
    }

    fig.update_layout(
        hovermode="closest",
        # map_style="white-bg",
        # map_layers=map_layers,
        map=map_dict,
    )

    # attach `customdata` with sample ids to each trace so callbacks can
    # identify points across traces (Plotly/px may create multiple traces
    # when coloring by group).
    sample_ids = df["sample_id"].astype(str).tolist()

    for trace in fig.data:
        # determine number of points in this trace (scattermapbox traces
        # expose `lat`/`lon` arrays)
        if "lat" in trace:
            n_pts = len(trace["lat"])
        else:
            n_pts = 0
        trace["customdata"] = sample_ids[:n_pts]

    return fig


def _validate_sample_name(sample_id: str | None):
    """coerce "C-12 map 2" etc. to "C-12" """
    if sample_id is None:
        return None
    return sample_id.split(" ")[0]


def highlight_selected_point_in_figure(
    figure: dict | go.Figure, sample_id: str | None, metadata: list[dict] | None = None
):
    """Return a modified figure with the point matching `sample_id` selected.

    The function looks for traces that include `customdata` (set to sample ids)
    and sets `trace['selectedpoints']` to the index of the matching point.
    If no match is found, any existing `selectedpoints` entries are cleared.
    """

    if figure is None:
        return figure

    # work with a JSON-serializable dict representation
    if hasattr(figure, "to_plotly_json"):
        fig = figure.to_plotly_json()
    else:
        fig = dict(figure)

    valid_sample_id = _validate_sample_name(sample_id)
    lat: None | float = None
    lon: None | float = None
    if metadata is not None:
        df = pd.DataFrame(metadata["records"])
        df_id = df[df.sample_id == valid_sample_id]
        if len(df_id) == 1:
            lat = float(df_id.iloc[0].lat)
            lon = float(df_id.iloc[0].lon)

    # Track a new center if we find a selected point
    new_center = None
    for trace in fig.get("data", []):
        custom = trace.get("customdata", []) or []
        sel_idx = None
        if valid_sample_id not in (None, "none"):
            for i, v in enumerate(custom):
                if str(v) == str(valid_sample_id):
                    sel_idx = i
                    break

        if sel_idx is not None:
            trace["selectedpoints"] = [sel_idx]
            try:
                if lat is not None and lon is not None:
                    new_center = {"lat": lat, "lon": lon}
            except RuntimeError:
                spectraLogger.exception("Failed to extract lat/lon for selected point")
        # clear selection for this trace
        elif "selectedpoints" in trace:
            trace["selectedpoints"] = []

    # ensure selection persists sensibly across updates
    fig.setdefault("layout", {})
    fig["layout"].setdefault("uirevision", "samplemap-selection")

    # If we found a center from a selected point, update the map center
    if new_center:
        fig["layout"].setdefault("map", {})
        # keep other map settings (zoom/bearing) intact if present
        fig["layout"]["map"]["center"] = new_center

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
                        config={
                            "modeBarButtonsToRemove": [
                                "lasso2d",
                                "select2d",
                            ]
                        },
                        style={
                            "aspectRatio": "1 / 1",  # or "4 / 3", "16 / 9", etc.
                            "width": "100%",
                        },
                    ),
                    width=12,
                )
            ),
        ]
    )
    return layout, IDS

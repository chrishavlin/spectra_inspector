from dataclasses import dataclass

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import MATCH, Input, Output, State, callback, dcc, no_update

from spectra_inspector.components.layout_ids import indexedLayoutIDMapper
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

    if available_data is None:
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
        hd_cols = [
            "group_name",
            "sample_type",
            "description",
            "lat",
            "lon",
            "elevation",
        ]

    # https://plotly.github.io/plotly.py-docs/generated/plotly.express.scatter_map.html
    fig = px.scatter_map(
        df,
        lat="lat",
        lon="lon",
        color="group_name",
        hover_name="sample_id",
        hover_data=hd_cols,
        map_style=map_style,
        size="marker_size",
        opacity=1.0,
        height=1000,  # width=1000
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
                    dcc.Graph(figure=fig, id=IDS.get_id_with_index("samplemap")),
                    width=12,
                )
            ),
        ]
    )
    return layout, IDS


_sample_map_IDs = sampleMapLayoutIDs(index=0)


@callback(
    Output({"type": _sample_map_IDs.samplemap, "index": MATCH}, "figure"),
    [Input({"type": _sample_map_IDs.dropdown, "index": MATCH}, "value")],
    [State({"type": _sample_map_IDs.samplemap, "index": MATCH}, "figure")],
)
def toggle_energy_slider_collapse(
    new_map_style: None | str, current_figure: None | go.Figure
):

    if new_map_style is None or current_figure is None:
        return no_update

    valid_style = _map_styles[new_map_style]
    if current_figure["layout"]["map"]["style"] == valid_style:
        return no_update

    current_figure["layout"]["map"]["style"] = valid_style
    return current_figure

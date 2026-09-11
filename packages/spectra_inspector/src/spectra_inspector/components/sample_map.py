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
        center = _default_center(None)
        hd_cols = ["group_name", "lat", "lon", "elevation"]

    else:
        records = available_data.sample_metadata.records or []
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

    return fig


def _sample_id_from_customdata(point_data) -> str | None:
    """Return the sample id stored as the last `customdata` column for a point."""
    if isinstance(point_data, (list, tuple, np.ndarray)):
        if len(point_data) == 0:
            return None
        return str(point_data[-1])
    return str(point_data)


def _validate_sample_name(sample_id: str | None):
    """coerce "C-12 map 2" etc. to "C-12" """
    if sample_id is None:
        return None
    return sample_id.split(" ")[0]


def highlight_selected_point_in_figure(
    figure: dict | go.Figure, sample_id: str | None, metadata: dict | None = None
):
    """Return a modified figure with the point matching `sample_id` selected.

    The function looks for traces that include `customdata` (whose last column
    holds sample ids) and sets `trace['selectedpoints']` to the index of the
    matching point, centering the map on it. If no match is found, every
    selection is cleared and the map recenters on the default location (see
    `_default_center`).
    """

    if figure is None:
        return figure

    # work with a JSON-serializable dict representation
    if hasattr(figure, "to_plotly_json"):
        fig = figure.to_plotly_json()
    else:
        fig = dict(figure)

    valid_sample_id = _validate_sample_name(sample_id)

    records_df: pd.DataFrame | None = None
    if metadata is not None and metadata.get("records"):
        records_df = pd.DataFrame(metadata["records"])

    selected_center: dict[str, float] | None = None
    if records_df is not None and "sample_id" in records_df:
        df_id = records_df[records_df.sample_id == valid_sample_id]
        if len(df_id) == 1:
            lat = pd.to_numeric(df_id.iloc[0].get("lat"), errors="coerce")
            lon = pd.to_numeric(df_id.iloc[0].get("lon"), errors="coerce")
            if pd.notna(lat) and pd.notna(lon):
                selected_center = {"lat": float(lat), "lon": float(lon)}

    matched = False
    for trace in fig.get("data", []):
        custom = trace.get("customdata", []) or []
        sel_idx = None
        if valid_sample_id not in (None, "none"):
            for i, v in enumerate(custom):
                if _sample_id_from_customdata(v) == str(valid_sample_id):
                    sel_idx = i
                    break

        if sel_idx is not None:
            matched = True
            trace["selectedpoints"] = [sel_idx]
        else:
            # an empty list is an explicit "nothing selected" for plotly,
            # which un-highlights whatever was selected before
            trace["selectedpoints"] = []

    # ensure selection persists sensibly across updates
    fig.setdefault("layout", {})
    fig["layout"].setdefault("uirevision", "samplemap-selection")

    if matched and selected_center is not None:
        new_center = selected_center
    else:
        new_center = _default_center(records_df)

    # keep other map settings (zoom/bearing/style) intact if present
    fig["layout"].setdefault("map", {})["center"] = new_center

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

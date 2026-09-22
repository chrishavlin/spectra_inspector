"""The summary export in the two dataset modes.

A map export writes every image panel (and the box subset of each) next to
the spectrum; a spectrum-only dataset has no images, so only the spectrum
files may come out, whatever panels the page happens to hold.
"""

import json
import zipfile
from pathlib import Path

import plotly.graph_objects as go
import pytest

from spectra_inspector.settings import ENV_PREFIX
from spectra_inspector.utilities import coerce
from spectra_inspector.utilities import model as m
from spectra_inspector.utilities.matplotib_importer import mpl_pyplot as plt


@pytest.fixture
def inspector(monkeypatch, tmp_path):
    monkeypatch.setenv(f"{ENV_PREFIX}DESKTOP_MODE", "false")
    monkeypatch.setenv(f"{ENV_PREFIX}WRITE_DIR", str(tmp_path))
    monkeypatch.setenv(f"{ENV_PREFIX}MAX_TMP_DIRS", "50")
    from spectra_inspector.main import app  # noqa: F401
    from spectra_inspector.pages import inspector

    # image panels reach the callback as figures serialised by the browser,
    # whose heatmap payload is not what plotly builds in python; a stand-in
    # figure keeps the test on which files are written, not on that parsing.
    real = coerce.plotly_to_matplotlib

    def convert(fig, **kwargs):
        if fig["data"][0]["type"] == "heatmap":
            return plt.figure()
        return real(fig, **kwargs)

    monkeypatch.setattr(inspector, "plotly_to_matplotlib", convert)

    # the export record needs the combined metadata, which the store lacks
    # here and would otherwise be fetched from a server that is not running
    monkeypatch.setattr(
        inspector.UserStore,
        "conditionally_fetch_metadata",
        lambda _self: combined_metadata(),
    )
    return inspector


def _axis(index: int, name: str, size: int, scale: float) -> m.EDAX_axis:
    return m.EDAX_axis(
        size=size,
        index_in_array=index,
        name=name,
        scale=scale,
        offset=0.0,
        units="µm" if name != "Energy" else "keV",
        navigate=name != "Energy",
    )


def combined_metadata(shape: tuple[int, int] = (2, 2)) -> m.CombinedMetadata:
    return m.CombinedMetadata(
        metadata=_metadata_model(),
        axes_by_index={
            "0": _axis(0, "y", shape[0], 1.5),
            "1": _axis(1, "x", shape[1], 2.0),
            "2": _axis(2, "Energy", 3, 0.5),
        },
        data_shape=[*shape, 3],
    )


def _metadata_model() -> m.MetadataModel:
    return m.MetadataModel(
        General=m.GeneralMetadata(original_filename="unittest.spc", title="unit"),
        Signal=m.Signal(signal_type="EDS"),
        Acquisition_instrument=m.AcquisitionInstrument(
            SEM=m.SEM(
                beam_energy=15.0,
                Stage=m.Stage(tilt_alpha=0.0),
                Detector=m.Detector(
                    EDS=m.EDS(
                        azimuth_angle=0.0,
                        elevation_angle=33.5,
                        energy_resolution_MnKa=125.0,
                        live_time=100.0,
                    )
                ),
            )
        ),
        Sample=m.Sample(elements=[]),
    )


@pytest.fixture
def spectrum_figure() -> dict:
    return go.Figure(go.Scatter(x=[0.0, 0.5, 1.0], y=[1.0, 2.0, 3.0])).to_plotly_json()


@pytest.fixture
def image_figures() -> list[dict]:
    fig = go.Figure(go.Heatmap(z=[[1, 2], [3, 4]])).to_plotly_json()
    return [fig, fig]


@pytest.fixture
def spectrum_metadata() -> dict:
    return {
        "energy": [0.0, 0.5, 1.0],
        "intensity": [1.0, 2.0, 3.0],
        "attrs": {
            "metadata": _metadata_model().model_dump(),
            "original_metadata": {},
            "weights": {"Fe": 0.5, "Si": 0.25},
            "integration_ranges_keV": {"Fe": [6.275, 6.54], "Si": [1.645, 1.88]},
        },
    }


def _zip_file(write_dir: Path) -> zipfile.ZipFile:
    zips = list(write_dir.glob("*/*.zip"))
    assert len(zips) == 1
    return zipfile.ZipFile(zips[0])


def _written_files(write_dir: Path) -> set[str]:
    return set(_zip_file(write_dir).namelist())


def _exported_metadata(write_dir: Path) -> dict:
    return json.loads(_zip_file(write_dir).read("metadata.json"))


def _export(inspector, image_figures, spectrum_figure, metadata, **kwargs):
    args = {
        "export_clicks": 1,
        "fig_list": image_figures,
        "shapes_store": {"active_shapes": []},
        "sample_name": "C-12",
        "slider_range_list": [[0.0, 1.0]] * len(image_figures),
        "slider_range_labels": ["none", "Fe"][: len(image_figures)],
        "spectrum_figure": spectrum_figure,
        "colormaps": ["viridis"] * len(image_figures),
        "user_store_dict": {"selected_dataset": "C-12", "spectrum_only": False},
        "export_summary_format": ".zip",
        "active_spectrum_metadata": metadata,
        "msafileformat": "XY",
        "zeroed_elements": [],
        "spectrum_yaxis_scale": "linear",
    }
    args.update(kwargs)
    return inspector.export_summary(**args)


SPECTRUM_FILES = {
    "spectrum.png",
    "spectrum.msa",
    "spectrum.csv",
    "ElementWeights.txt",
    "metadata.json",
    "README.txt",
}


def test_spectrum_export_follows_the_peak_window_switch(
    inspector, image_figures, spectrum_figure, spectrum_metadata, monkeypatch
):
    # the exported spectrum gets its windows from the switch and the active
    # spectrum, not from whatever the page's figure happens to hold (issue #120)
    seen = []
    convert = inspector.plotly_to_matplotlib

    def capture(fig, **kwargs):
        if fig["data"][0]["type"] != "heatmap":
            seen.append(fig)
        return convert(fig, **kwargs)

    monkeypatch.setattr(inspector, "plotly_to_matplotlib", capture)
    for show in (True, False):
        _export(
            inspector,
            image_figures,
            spectrum_figure,
            spectrum_metadata,
            show_peak_windows=show,
        )

    shown, hidden = seen
    assert {s["name"] for s in shown["layout"]["shapes"]} == {"Fe", "Si"}
    assert [a["text"] for a in shown["layout"]["annotations"]] == ["Fe", "Si"]
    assert hidden["layout"]["shapes"] == []
    assert hidden["layout"]["annotations"] == []
    assert len(hidden["data"]) == 1
    assert "shapes" not in spectrum_figure["layout"]


def test_spectrum_export_drops_zeroed_out_peaks(
    inspector, image_figures, spectrum_figure, spectrum_metadata, monkeypatch
):
    seen = []
    convert = inspector.plotly_to_matplotlib

    def capture(fig, **kwargs):
        if fig["data"][0]["type"] != "heatmap":
            seen.append(fig)
        return convert(fig, **kwargs)

    monkeypatch.setattr(inspector, "plotly_to_matplotlib", capture)
    _export(
        inspector,
        image_figures,
        spectrum_figure,
        spectrum_metadata,
        zeroed_elements=["Fe"],
    )

    (fig,) = seen
    assert [s["name"] for s in fig["layout"]["shapes"]] == ["Si"]
    assert [a["text"] for a in fig["layout"]["annotations"]] == ["Si"]


def test_map_zip_includes_every_panel(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path
):
    result = _export(inspector, image_figures, spectrum_figure, spectrum_metadata)
    assert result["filename"].endswith(".zip")
    assert _written_files(tmp_path) == SPECTRUM_FILES | {
        "bitmap_00.png",
        "bitmap_01_Fe.png",
    }


def test_zip_metadata_describes_the_sample_and_the_box(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path
):
    # the zip carries what the data-selection accordion shows, the
    # box in index and physical units, and what each image file holds
    sample_sheet = {
        "records": [{"sample_id": "S1", "description": "a rock"}],
        "map_samples": {"C-12": "S1"},
    }
    # the box subset is cut from the image array, so the panels need the
    # heatmap payload in the form the browser serialises it
    browser_figure = {
        "data": [
            {
                "type": "heatmap",
                "z": {
                    "shape": "2, 2",
                    "_inputArray": [{"0": 1, "1": 2}, {"0": 3, "1": 4}],
                },
            }
        ],
        "layout": {},
    }
    _export(
        inspector,
        [browser_figure] * len(image_figures),
        spectrum_figure,
        spectrum_metadata,
        user_store_dict={
            "selected_dataset": "C-12",
            "spectrum_only": False,
            "sample_metadata": sample_sheet,
        },
        shapes_store={
            "active_shapes": [
                {"type": "rect", "x0": 0.2, "x1": 1.7, "y0": 1.9, "y1": 0.1}
            ]
        },
        zeroed_elements=["Si"],
        show_peak_windows=False,
    )
    record = _exported_metadata(tmp_path)

    assert record["dataset"] == "C-12"
    assert record["spectrum_only"] is False
    expected_sample = combined_metadata().model_dump()
    expected_sample["Sample Information"] = sample_sheet["records"][0]
    assert record["sample"] == expected_sample

    box = record["subselection"]
    assert box["shape"] == [1, 1]
    assert box["axes"]["index0"] == {
        "name": "y",
        "index_range": [0, 1],
        "bounds": [0.0, 1.5],
        "units": "µm",
    }
    assert box["axes"]["index1"] == {
        "name": "x",
        "index_range": [0, 1],
        "bounds": [0.0, 2.0],
        "units": "µm",
    }

    assert [im["file"] for im in record["images"]] == [
        "bitmap_00.png",
        "bitmap_01_Fe.png",
    ]
    assert record["images"][1]["subset_file"] == "bitmap_01_Fe_subset.png"
    assert record["spectrum"] == {
        "zeroed_elements": ["Si"],
        "peak_windows_shown": False,
    }

    readme = _zip_file(tmp_path).read("README.txt").decode("utf-8")
    written = _written_files(tmp_path)
    assert {"bitmap_00_subset.png", "bitmap_01_Fe_subset.png"} <= written
    for name in written:
        assert name in readme


def test_polygon_export_crops_to_the_pixel_rectangle_and_draws_the_outline(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path, monkeypatch
):
    browser_figure = {
        "data": [
            {
                "type": "heatmap",
                "z": {
                    "shape": "3, 3",
                    "_inputArray": [
                        {"0": 1, "1": 2, "2": 3},
                        {"0": 4, "1": 5, "2": 6},
                        {"0": 7, "1": 8, "2": 9},
                    ],
                },
            }
        ],
        "layout": {},
    }
    fulls, subsets = _capture_image_figures(inspector, monkeypatch)
    monkeypatch.setattr(
        inspector.UserStore,
        "conditionally_fetch_metadata",
        lambda _self: combined_metadata(shape=(3, 3)),
    )
    # (x, y) corners of a triangle: only the centre of pixel (1, 1) is inside
    # it, but its corners reach into the pixels around, so the crop is rows 1
    # to 2 and columns 0 to 2
    points = [[0.4, 0.6], [2.4, 1.0], [1.0, 2.4]]
    _export(
        inspector,
        [browser_figure] * len(image_figures),
        spectrum_figure,
        spectrum_metadata,
        shapes_store=inspector.polygon_store(points, points),
        outline_dot_color="#ff0000",
    )
    record = _exported_metadata(tmp_path)
    sub = record["subselection"]
    assert sub["kind"] == "polygon"
    assert sub["shape"] == [2, 3]
    assert sub["axes"]["index0"]["index_range"] == [1, 3]
    assert sub["axes"]["index1"]["index_range"] == [0, 3]
    assert sub["polygon"]["vertices_index"] == [[0.6, 0.4], [1.0, 2.4], [2.4, 1.0]]
    assert record["images"][1]["subset_file"] == "bitmap_01_Fe_subset.png"

    # every image carries the unfilled outline and a dot per corner in the
    # export's colours (the browser's translucent fill and start / end
    # colours are not copied); the subset's are shifted onto the crop
    assert len(fulls) == len(subsets) == len(image_figures)
    for fig in fulls:
        outline, *dots = fig["layout"]["shapes"]
        assert coerce.path_vertices(outline["path"]) == pytest.approx(
            [tuple(p) for p in points]
        )
        assert outline["fillcolor"] == "rgba(0,0,0,0)"
        assert outline["line"]["color"] == "#ffffff"
        assert [d["fillcolor"] for d in dots] == ["#ff0000"] * 3
    for fig in subsets:
        outline, *dots = fig["layout"]["shapes"]
        assert outline["type"] == "path"
        assert coerce.path_vertices(outline["path"]) == pytest.approx(
            [(0.4, -0.4), (2.4, 0.0), (1.0, 1.4)]
        )
        assert outline["fillcolor"] == "rgba(0,0,0,0)"
        assert [d["type"] for d in dots] == ["circle"] * 3

    written = _written_files(tmp_path)
    assert {"bitmap_00_subset.png", "bitmap_01_Fe_subset.png"} <= written
    readme = _zip_file(tmp_path).read("README.txt").decode("utf-8")
    assert "Polygon with 3 corners" in readme
    assert "Bounding box shape (rows, columns): 2, 3" in readme


def _capture_image_figures(inspector, monkeypatch) -> tuple[list, list]:
    """Record every image figure handed to the matplotlib conversion, as
    dicts: the panels' figures as the browser sent them (with the export's
    shapes put on) and the subsets built in python, in panel order."""
    fulls: list = []
    subsets: list = []
    convert = inspector.plotly_to_matplotlib

    def capture(fig, **kwargs):
        if fig["data"][0]["type"] == "heatmap":
            if kwargs.get("im_data") is None:
                fulls.append(fig)
            else:
                subsets.append(fig)
        return convert(fig, **kwargs)

    monkeypatch.setattr(inspector, "plotly_to_matplotlib", capture)
    return fulls, subsets


BOX_STORE = {
    "active_shapes": [
        {
            "type": "rect",
            "x0": 0.2,
            "x1": 1.7,
            "y0": 1.9,
            "y1": 0.1,
            "line": {"color": "orange"},
        }
    ]
}


def _browser_figure_with_box() -> dict:
    """A 2x2 heatmap as the browser serialises it, with the dragged box drawn
    on as plotly would."""
    return {
        "data": [
            {
                "type": "heatmap",
                "z": {
                    "shape": "2, 2",
                    "_inputArray": [{"0": 1, "1": 2}, {"0": 3, "1": 4}],
                },
            }
        ],
        "layout": {"shapes": BOX_STORE["active_shapes"]},
    }


def test_box_export_draws_the_selected_pixels_in_the_chosen_colour(
    inspector, image_figures, spectrum_figure, spectrum_metadata, monkeypatch
):
    fulls, subsets = _capture_image_figures(inspector, monkeypatch)
    browser_figure = _browser_figure_with_box()
    _export(
        inspector,
        [browser_figure] * len(image_figures),
        spectrum_figure,
        spectrum_metadata,
        shapes_store=BOX_STORE,
        outline_line_color="#000000",
    )
    # the box is the pixel it selected (row 0, column 0), drawn at that
    # pixel's edges rather than where the drag happened to land
    for fig in fulls:
        (rect,) = fig["layout"]["shapes"]
        assert (rect["x0"], rect["x1"], rect["y0"], rect["y1"]) == (
            -0.5,
            0.5,
            -0.5,
            0.5,
        )
        assert rect["line"]["color"] == "#000000"
    # the crop is the box: nothing is drawn over it
    assert len(subsets) == len(image_figures)
    assert all(fig["layout"].get("shapes", []) == [] for fig in subsets)


def test_box_past_the_image_edge_exports_the_part_inside(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path, monkeypatch
):
    # a box dragged out past the 2x2 map's edge (rows -1..1, columns -1..5):
    # the crop, the outline and the record are the row of pixels inside it
    fulls: list = []
    crops: list = []
    convert = inspector.plotly_to_matplotlib

    def capture(fig, **kwargs):
        if fig["data"][0]["type"] == "heatmap":
            if kwargs.get("im_data") is None:
                fulls.append(fig)
            else:
                crops.append(kwargs["im_data"])
        return convert(fig, **kwargs)

    monkeypatch.setattr(inspector, "plotly_to_matplotlib", capture)
    store = {
        "active_shapes": [
            {"type": "rect", "x0": -0.7, "x1": 5.0, "y0": 1.3, "y1": -1.0}
        ]
    }
    browser_figure = _browser_figure_with_box()
    browser_figure["layout"]["shapes"] = store["active_shapes"]
    _export(
        inspector,
        [browser_figure] * len(image_figures),
        spectrum_figure,
        spectrum_metadata,
        shapes_store=store,
    )

    box = _exported_metadata(tmp_path)["subselection"]
    assert box["shape"] == [1, 2]
    assert box["axes"]["index0"]["index_range"] == [0, 1]
    assert box["axes"]["index1"]["index_range"] == [0, 2]
    for fig in fulls:
        (rect,) = fig["layout"]["shapes"]
        assert (rect["x0"], rect["x1"], rect["y0"], rect["y1"]) == (
            -0.5,
            1.5,
            -0.5,
            0.5,
        )
    assert len(crops) == len(image_figures)
    assert all(crop.tolist() == [[1, 2]] for crop in crops)
    assert {"bitmap_00_subset.png", "bitmap_01_Fe_subset.png"} <= _written_files(
        tmp_path
    )


def test_export_leaves_the_selection_off_the_images_when_asked(
    inspector, image_figures, spectrum_figure, spectrum_metadata, monkeypatch
):
    fulls, subsets = _capture_image_figures(inspector, monkeypatch)
    browser_figure = _browser_figure_with_box()
    _export(
        inspector,
        [browser_figure] * len(image_figures),
        spectrum_figure,
        spectrum_metadata,
        shapes_store=BOX_STORE,
        include_outline=False,
    )
    assert len(fulls) == len(subsets) == len(image_figures)
    assert all(fig["layout"].get("shapes", []) == [] for fig in [*fulls, *subsets])


def test_figure_export_settings_show_once_there_is_a_selection(inspector):
    hidden = inspector.toggle_figure_export_settings
    assert hidden(None) is True
    assert hidden({"active_shapes": []}) is True
    assert hidden(BOX_STORE) is False
    points = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
    assert hidden(inspector.polygon_store(points, None)) is True
    assert hidden(inspector.polygon_store(points, points)) is False


def test_figure_export_settings_go_with_the_image_section(inspector):
    hidden = inspector.toggle_figure_export_settings_with_images
    assert hidden(True) is True
    assert hidden(False) is False


def _browser_figure_with_scalebar() -> dict:
    """The boxed 2x2 heatmap with the scalebar as a panel draws it: a green
    bar and label, tagged for the export."""
    figure = _browser_figure_with_box()
    figure["data"].append(
        {
            "type": "scatter",
            "x": [0, 1],
            "y": [0, 0],
            "line": {"color": "green", "width": 5},
            "meta": {"scalebar": True},
        }
    )
    figure["layout"]["annotations"] = [
        {
            "name": "scalebar",
            "text": "1.6 µm",
            "x": 0.5,
            "y": 0,
            "font": {"color": "green", "size": 12, "weight": 1000},
        }
    ]
    return figure


def _scalebar_of(figure: dict) -> tuple[dict | None, dict | None]:
    bars = [t for t in figure["data"] if (t.get("meta") or {}).get("scalebar")]
    labels = [
        a
        for a in figure["layout"].get("annotations", [])
        if a.get("name") == "scalebar"
    ]
    assert len(bars) <= 1
    assert len(labels) <= 1
    return (bars[0] if bars else None, labels[0] if labels else None)


def test_export_draws_the_scalebar_as_the_figure_settings_say(
    inspector, image_figures, spectrum_figure, spectrum_metadata, monkeypatch
):
    fulls, subsets = _capture_image_figures(inspector, monkeypatch)
    _export(
        inspector,
        [_browser_figure_with_scalebar()] * len(image_figures),
        spectrum_figure,
        spectrum_metadata,
        shapes_store=BOX_STORE,
        scalebar_color="#ff0000",
        scalebar_fontsize=14,
    )
    # the panels' figures and the subsets built here alike: the browser's
    # green is replaced, the label resized, the bar's length left alone
    assert len(fulls) == len(subsets) == len(image_figures)
    for figure in [*fulls, *subsets]:
        bar, label = _scalebar_of(figure)
        assert bar is not None
        assert label is not None
        assert bar["line"]["color"] == "#ff0000"
        assert label["font"]["color"] == "#ff0000"
        assert label["font"]["size"] == 14
    assert fulls[0]["data"][1]["x"] == [0, 1]


def test_export_leaves_the_scalebar_off_the_images_when_asked(
    inspector, image_figures, spectrum_figure, spectrum_metadata, monkeypatch
):
    fulls, subsets = _capture_image_figures(inspector, monkeypatch)
    _export(
        inspector,
        [_browser_figure_with_scalebar()] * len(image_figures),
        spectrum_figure,
        spectrum_metadata,
        shapes_store=BOX_STORE,
        include_scalebar=False,
    )
    assert len(fulls) == len(subsets) == len(image_figures)
    for figure in [*fulls, *subsets]:
        assert _scalebar_of(figure) == (None, None)
        assert figure["data"][0]["type"] == "heatmap"
    # the box is still drawn on the full images
    assert all(len(figure["layout"]["shapes"]) == 1 for figure in fulls)


def test_polygon_in_progress_exports_the_full_map(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path
):
    points = [[0.0, 1.0], [0.9, 1.0], [0.0, 1.9]]
    _export(
        inspector,
        image_figures,
        spectrum_figure,
        spectrum_metadata,
        shapes_store=inspector.polygon_store(points, None),
    )
    record = _exported_metadata(tmp_path)
    assert record["subselection"] is None
    assert all(im["subset_file"] is None for im in record["images"])


def test_export_survives_an_unreachable_server(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path, monkeypatch
):
    def unreachable(_self):
        msg = "could not reach the backend"
        raise inspector.ServerRequestError(msg)

    monkeypatch.setattr(
        inspector.UserStore, "conditionally_fetch_metadata", unreachable
    )
    _export(inspector, image_figures, spectrum_figure, spectrum_metadata)
    record = _exported_metadata(tmp_path)
    assert record["sample"] is None
    assert record["dataset"] == "C-12"


def test_spectrum_only_zip_has_no_bitmaps(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path
):
    # a rectangle and two panels on the page must not produce any image file
    result = _export(
        inspector,
        image_figures,
        spectrum_figure,
        spectrum_metadata,
        user_store_dict={"selected_dataset": "C-12", "spectrum_only": True},
        shapes_store={
            "active_shapes": [{"type": "rect", "x0": 0, "x1": 1, "y0": 0, "y1": 1}]
        },
    )
    assert result["filename"].endswith(".zip")
    assert _written_files(tmp_path) == SPECTRUM_FILES


def test_spectrum_only_falls_back_to_the_switch(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path
):
    _export(
        inspector,
        image_figures,
        spectrum_figure,
        spectrum_metadata,
        user_store_dict={"selected_dataset": "C-12"},
        spectrum_only_switch=True,
    )
    assert _written_files(tmp_path) == SPECTRUM_FILES


def test_spectrum_only_pdf(
    inspector, image_figures, spectrum_figure, spectrum_metadata, tmp_path
):
    result = _export(
        inspector,
        image_figures,
        spectrum_figure,
        spectrum_metadata,
        user_store_dict={"selected_dataset": "C-12", "spectrum_only": True},
        export_summary_format="PDF",
    )
    assert result["filename"].endswith(".pdf")
    written = {f.name for f in tmp_path.glob("*/*/*") if f.is_file()}
    assert written == {"spectrum.png", "SpectraInspectorSummary.pdf"}

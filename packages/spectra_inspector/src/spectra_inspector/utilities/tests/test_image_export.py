import numpy as np
import pytest
from matplotlib.colors import Normalize

from spectra_inspector.utilities import image_export
from spectra_inspector.utilities.coerce import plotly_to_matplotlib
from spectra_inspector.utilities.image_export import (
    MIN_IMAGE_SIDE,
    PAGE_IMAGE_SIDE,
    export_image_size,
    image_axes,
    page_scale_factor,
    reduce_image,
    render_image_figure,
)
from spectra_inspector.utilities.matplotib_importer import mpl_pyplot as plt

ROWS, COLS = 700, 900


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _figure(z: np.ndarray, shapes: list[dict] | None = None, **kwargs):
    fig = {"data": [{"type": "heatmap"}], "layout": {"shapes": shapes or []}}
    return plotly_to_matplotlib(fig, im_data=z, cmap="viridis", **kwargs)


def _viridis(z: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return plt.get_cmap("viridis")(Normalize(lo, hi)(z), bytes=True)[..., :3]


@pytest.fixture
def z() -> np.ndarray:
    return np.random.default_rng(0).integers(0, 1000, (ROWS, COLS))


def test_every_map_pixel_is_written_as_itself(z):
    out = np.asarray(render_image_figure(_figure(z)))
    assert out.shape == (ROWS, COLS, 3)
    np.testing.assert_array_equal(out, _viridis(z, z.min(), z.max()))


def test_an_rgb_image_is_written_as_it_is():
    rgb = np.random.default_rng(1).integers(0, 256, (ROWS, COLS, 3), dtype=np.uint8)
    fig = plotly_to_matplotlib({"data": [{"type": "image"}], "layout": {}}, im_data=rgb)
    np.testing.assert_array_equal(np.asarray(render_image_figure(fig)), rgb)


def test_the_outline_lands_on_the_pixels_it_names():
    z = np.zeros((ROWS, COLS), dtype=np.int64)
    box = {
        "type": "rect",
        "x0": 100,
        "x1": 300,
        "y0": 200,
        "y1": 500,
        "line": {"color": "#ff0000"},
    }
    out = np.asarray(render_image_figure(_figure(z, [box]))).astype(int)
    assert out.shape == (ROWS, COLS, 3)

    background = out[0, 0]
    drawn_rows, drawn_cols = np.nonzero((out != background).any(axis=2))
    # a pixel's centre sits half a pixel into it, and the line straddles the
    # box's edge by half its own width on either side
    assert (drawn_cols.min() + drawn_cols.max() + 1) / 2 == pytest.approx(200.5, abs=1)
    assert (drawn_rows.min() + drawn_rows.max() + 1) / 2 == pytest.approx(350.5, abs=1)
    line = (drawn_cols.max() + 1 - drawn_cols.min()) - 200
    assert 1 <= line <= 12
    assert (drawn_rows.max() + 1 - drawn_rows.min()) - 300 == pytest.approx(line, abs=1)
    # the outline is not filled
    np.testing.assert_array_equal(out[350, 200], background)
    assert tuple(out[350, 100]) == (255, 0, 0)


def test_the_title_goes_in_a_strip_above_the_map(z):
    out = np.asarray(render_image_figure(_figure(z, title="Fe")))
    strip = out.shape[0] - ROWS
    assert strip > 0
    assert out.shape[1] == COLS
    np.testing.assert_array_equal(out[strip:], _viridis(z, z.min(), z.max()))
    # dark lettering on a white strip
    assert (out[:strip] == 255).all(axis=2).mean() > 0.5
    assert (out[:strip] < 128).all(axis=2).any()


def test_a_long_title_is_fitted_to_a_narrow_map():
    z = np.zeros((1200, 300), dtype=np.int64)
    title = "Mg (#ff0000) + Al (#00ff00) + Si (#0000ff)"
    out = np.asarray(render_image_figure(_figure(z, title=title)))
    strip = out.shape[0] - 1200
    inked = np.nonzero((out[:strip] < 128).all(axis=2))[1]
    assert inked.min() > 0
    assert inked.max() < 299


def test_a_scale_factor_averages_blocks_of_pixels(z):
    out = np.asarray(render_image_figure(_figure(z), factor=2))
    assert out.shape == (350, 450, 3)
    means = z.reshape(350, 2, 450, 2).mean(axis=(1, 3))
    # coloured on the full map's range, so the sizes share their colours
    np.testing.assert_array_equal(out, _viridis(means, z.min(), z.max()))


def test_a_small_map_is_enlarged_in_whole_pixels():
    z = np.arange(16 * 24).reshape(16, 24)
    out = np.asarray(render_image_figure(_figure(z)))
    assert out.shape[:2] == export_image_size((16, 24), 1) == (176, 264)
    expected = np.kron(
        _viridis(z, z.min(), z.max()), np.ones((11, 11, 1), dtype=np.uint8)
    )
    np.testing.assert_array_equal(out, expected)


def test_reduce_image_averages_the_pixels_an_edge_block_has():
    image = np.array([[1, 3, 10], [5, 7, 20], [100, 200, 300]])
    np.testing.assert_allclose(reduce_image(image, 2), [[4.0, 15.0], [150.0, 300.0]])
    assert reduce_image(image, 1) is image

    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[0, 0] = (255, 100, 1)
    reduced = reduce_image(rgb, 2)
    assert reduced.dtype == np.uint8
    np.testing.assert_array_equal(reduced, [[[64, 25, 0]]])


def test_sizes():
    assert export_image_size((2048, 1536), 1) == (2048, 1536)
    assert export_image_size((2048, 1536), 4) == (512, 384)
    # 1001 pixels cannot be halved evenly: the last block is cut short
    assert export_image_size((1001, 1000), 2) == (501, 500)
    small = export_image_size((100, 50), 1)
    assert max(small) >= MIN_IMAGE_SIDE
    assert small[0] == 2 * small[1]

    assert page_scale_factor((512, 512)) == 1
    assert page_scale_factor((PAGE_IMAGE_SIDE, 10)) == 1
    assert page_scale_factor((4096, 2048)) == 3
    assert max(export_image_size((4096, 2048), 3)) <= PAGE_IMAGE_SIDE


def test_only_a_lone_image_counts_as_an_image_figure(z):
    assert image_axes(_figure(z)) is not None
    assert image_axes(_figure(z, include_colorbar=True)) is None
    line = plt.figure()
    line.add_subplot(111).plot([0, 1], [0, 1])
    assert image_axes(line) is None
    with pytest.raises(ValueError, match="single image"):
        image_export.render_image_figure(line)

import numpy as np
import plotly.express as px
import pytest

from spectra_inspector.utilities import composite as c
from spectra_inspector.utilities.coerce import (
    plotly_image_trace_to_array,
    plotly_to_matplotlib,
)
from spectra_inspector.utilities.matplotib_importer import mpl_pyplot as plt


def _channel(element="Fe", color="red", stretch=c.DEFAULT_STRETCH, rng=(6.0, 6.5)):
    return c.compositeChannel(element, rng, color, stretch)


class TestColors:
    def test_palette_names_and_hex_both_work(self):
        assert c.color_rgb("red") == (1.0, 0.0, 0.0)
        assert c.color_rgb("#00ff00") == (0.0, 1.0, 0.0)
        assert c.color_hex("cyan") == "#00ffff"
        assert c.color_hex("#123456") == "#123456"

    def test_unknown_colour_is_rejected(self):
        with pytest.raises(ValueError, match="unrecognised"):
            c.color_rgb("chartreuse")

    def test_swatch_text_reads_on_light_and_dark(self):
        assert c.text_color_for("white") == "#000000"
        assert c.text_color_for("yellow") == "#000000"
        assert c.text_color_for("blue") == "#ffffff"


class TestNormalize:
    def test_min_max_stretch(self):
        im = np.array([[0, 5], [10, 20]])
        out = c.normalize_channel(im)
        assert out.tolist() == [[0.0, 0.25], [0.5, 1.0]]

    def test_percentiles_clip_the_tails(self):
        im = np.arange(101, dtype=float)
        out = c.normalize_channel(im, (10.0, 90.0))
        assert out[:11].tolist() == [0.0] * 11
        assert out[90:].tolist() == [1.0] * 11
        assert out[50] == pytest.approx(0.5)

    def test_reversed_percentiles_are_sorted(self):
        im = np.arange(101, dtype=float)
        assert np.array_equal(
            c.normalize_channel(im, (90.0, 10.0)), c.normalize_channel(im, (10.0, 90.0))
        )

    def test_flat_map_is_black(self):
        assert not c.normalize_channel(np.full((2, 2), 7.0)).any()


class TestCompositeRGB:
    def test_primaries_mix_additively(self):
        fe = np.array([[0, 10], [10, 10]])
        ca = np.array([[0, 0], [10, 10]])
        rgb = c.composite_rgb(
            [_channel("Fe", "red"), _channel("Ca", "green")], [fe, ca]
        )
        assert rgb.dtype == np.uint8
        assert rgb[0, 0].tolist() == [0, 0, 0]
        assert rgb[0, 1].tolist() == [255, 0, 0]
        assert rgb[1, 0].tolist() == [255, 255, 0]

    def test_each_channel_is_normalised_on_its_own(self):
        # counts two orders of magnitude apart still both reach full tint
        weak = np.array([[0, 1]])
        strong = np.array([[0, 100]])
        rgb = c.composite_rgb(
            [_channel(color="red"), _channel(color="blue")], [weak, strong]
        )
        assert rgb[0, 1].tolist() == [255, 0, 255]

    def test_sum_is_clipped(self):
        im = np.array([[0, 10]])
        rgb = c.composite_rgb(
            [_channel(color="red"), _channel(color="yellow")], [im, im]
        )
        assert rgb[0, 1].tolist() == [255, 255, 0]

    def test_off_channels_take_no_array(self):
        channels = [_channel("Fe", "red"), _channel(c.CHANNEL_OFF, "green")]
        rgb = c.composite_rgb(channels, [np.array([[0, 1]])])
        assert rgb[0, 1].tolist() == [255, 0, 0]
        with pytest.raises(ValueError, match="active channels"):
            c.composite_rgb(channels, [np.array([[0, 1]])] * 2)

    def test_nothing_active_is_black_at_the_given_shape(self):
        rgb = c.composite_rgb([_channel(c.CHANNEL_OFF)], [], shape=(2, 3))
        assert rgb.shape == (2, 3, 3)
        assert not rgb.any()
        with pytest.raises(ValueError, match="shape"):
            c.composite_rgb([_channel(c.CHANNEL_OFF)], [])


class TestChannelText:
    def test_hover_names_the_primaries_by_element(self):
        template = c.hover_template(
            [
                _channel("Fe", "red"),
                _channel("Ca", "green"),
                _channel(c.CHANNEL_OFF, "blue"),
            ]
        )
        assert template.startswith(
            "Fe (red): %{z[0]}<br>Ca (green): %{z[1]}<br>blue: %{z[2]}"
        )
        assert template.endswith("<extra></extra>")

    def test_hover_falls_back_when_hues_mix(self):
        template = c.hover_template([_channel("Fe", "red"), _channel("Ca", "yellow")])
        assert template.startswith("red: %{z[0]}<br>green: %{z[1]}<br>blue: %{z[2]}")
        # two channels on one primary are not separable either
        template = c.hover_template([_channel("Fe", "red"), _channel("Ca", "red")])
        assert template.startswith("red: %{z[0]}")

    def test_labels_and_summary(self):
        custom = _channel(c.CUSTOM_RANGE, "cyan", rng=(1.0, 2.5))
        assert custom.label == "1-2.5 keV"
        assert _channel("Fe").label == "Fe"
        assert c.channel_summary(
            [_channel("Fe", "red"), custom, _channel(c.CHANNEL_OFF)]
        ) == ("Fe red, 1-2.5 keV cyan")

    def test_metadata_record(self):
        record = _channel(c.CUSTOM_RANGE, "cyan", (1.0, 99.0), (1.0, 2.5)).metadata()
        assert record == {
            "active": True,
            "element": None,
            "energy_range_keV": [1.0, 2.5],
            "color": "cyan",
            "color_hex": "#00ffff",
            "stretch_percentiles": [1.0, 99.0],
        }
        assert _channel("Fe").metadata()["element"] == "Fe"
        off = _channel(c.CHANNEL_OFF).metadata()
        assert off["active"] is False
        assert off["element"] is None


class TestImageTraceRoundTrip:
    @pytest.fixture
    def rgb(self):
        rng = np.random.default_rng(0)
        return rng.integers(0, 256, size=(4, 5, 3), dtype=np.uint8)

    def test_png_source_decodes_to_the_pixels(self, rgb):
        trace = px.imshow(rgb).to_plotly_json()["data"][0]
        assert trace["type"] == "image"
        assert trace["source"].startswith("data:image/png;base64,")
        assert np.array_equal(plotly_image_trace_to_array(trace), rgb)

    def test_z_array_is_accepted_too(self, rgb):
        assert np.array_equal(plotly_image_trace_to_array({"z": rgb.tolist()}), rgb)
        with pytest.raises(ValueError, match="neither"):
            plotly_image_trace_to_array({"type": "image"})

    def test_matplotlib_export_of_an_rgb_image(self, rgb):
        fig = px.imshow(rgb)
        fig.update_layout(shapes=[{"type": "rect", "x0": 0, "x1": 2, "y0": 0, "y1": 1}])
        mpl_fig = plotly_to_matplotlib(fig.to_plotly_json(), include_colorbar=True)
        assert mpl_fig is not None
        (ax,) = mpl_fig.axes
        assert np.array_equal(ax.images[0].get_array(), rgb)
        assert len(ax.patches) == 1
        plt.close(mpl_fig)

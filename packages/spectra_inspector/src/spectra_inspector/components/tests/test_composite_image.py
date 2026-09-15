import numpy as np
import pytest

from spectra_inspector.components import composite_image as ci
from spectra_inspector.components.scalebar import scalebarHandler
from spectra_inspector.tests.test_export_summary import combined_metadata
from spectra_inspector.utilities.composite import (
    CHANNEL_OFF,
    CUSTOM_RANGE,
    compositeChannel,
)

_RANGES = {"Al": (1.40, 1.61), "Mg": (1.13, 1.34), "Si": (1.65, 1.88)}
_PATCH_TARGET = (
    "spectra_inspector.components.energy_range_slider.get_element_energy_ranges"
)


@pytest.fixture
def server_ranges(mocker):
    mocker.patch(_PATCH_TARGET, return_value=dict(_RANGES))
    return _RANGES


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, list):
        children = [children]
    for child in children:
        yield from _walk(child)


def _ids(component) -> list[dict]:
    return [c.id for c in _walk(component) if isinstance(getattr(c, "id", None), dict)]


def _of_type(component, id_type: str) -> list:
    return [
        c
        for c in _walk(component)
        if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == id_type
    ]


@pytest.mark.parametrize(
    "mapper", [ci.compositeImageLayoutIDs, ci.compositeChannelLayoutIDs]
)
def test_id_props_round_trip(mapper):
    ids = mapper()
    for prop in ids.prop_names:
        assert getattr(ids, prop) == f"{ids.id_type_base}-{prop}"


def test_channel_index_round_trips():
    assert ci.channel_index(4, 2) == "4-2"
    assert ci.split_channel_index("4-2") == (4, 2)


@pytest.mark.usefixtures("server_ranges")
def test_layout_shares_the_panel_ids_and_owns_the_channel_ids():
    card, _ = ci.composite_image_layout(7)
    ids = _ids(card)

    # the pieces the inspector's shared callbacks key on
    assert card.id == {"type": "bitmap-image-div", "index": 7}
    assert {"type": "bitmap-image-graph", "index": 7} in ids
    assert {"type": "bitmap-image-delete", "index": 7} in ids
    assert {"type": "composite-image-apply", "index": 7} in ids
    # and none of a single panel's controls
    assert not any(id_["type"].startswith("element-dropdown-slider") for id_ in ids)
    assert not any(id_["type"] == "bitmap-image-colorscale" for id_ in ids)

    for channel in range(ci.MAX_CHANNELS):
        cid = ci.channel_index(7, channel)
        for id_type in (
            "composite-channel-selector-dropdown",
            "composite-channel-selector-slider",
            "composite-channel-badge",
            "composite-channel-color",
            "composite-channel-stretch",
        ):
            assert {"type": id_type, "index": cid} in ids
    # the slider is mounted once, in the details, not in the selector's collapse
    assert not any(id_["type"] == "composite-channel-selector-collapse" for id_ in ids)


@pytest.mark.usefixtures("server_ranges")
def test_channel_dropdowns_offer_off_and_custom():
    card, _ = ci.composite_image_layout(0)
    dropdowns = _of_type(card, "composite-channel-selector-dropdown")
    assert [d.value for d in dropdowns] == ["Mg", "Al", "Si"]
    for dropdown in dropdowns:
        assert dropdown.options[0] == CUSTOM_RANGE
        assert dropdown.options[-1] == CHANNEL_OFF
        assert "none" not in dropdown.options


@pytest.mark.usefixtures("server_ranges")
def test_badges_carry_the_channel_colours():
    card, _ = ci.composite_image_layout(0)
    badges = _of_type(card, "composite-channel-badge")
    assert [b.color for b in badges] == ["#ff0000", "#00ff00", "#0000ff"]
    assert [b.children for b in badges] == ["1", "2", "3"]
    assert ci.recolor_channel_badge("yellow") == ("#ffff00", {"color": "#000000"})


def test_channel_specs_regroup_per_panel():
    ids = [
        {"type": "x", "index": "0-0"},
        {"type": "x", "index": "0-1"},
        {"type": "x", "index": "0-2"},
        {"type": "x", "index": "3-0"},
    ]
    specs = ci.channel_specs_from_states(
        ["Mg", CHANNEL_OFF, CUSTOM_RANGE, "Fe"],
        ids,
        [[1.1, 1.3], [1.4, 1.6], [2.0, 3.0], [6.2, 6.5]],
        ids,
        ["red", "green", "cyan", "white"],
        ids,
        [[0, 100], [0, 100], [1, 99], [0, 100]],
        ids,
    )
    assert set(specs) == {0, 3}
    assert specs[0] == [
        compositeChannel("Mg", (1.1, 1.3), "red", (0.0, 100.0)),
        compositeChannel(CHANNEL_OFF, (1.4, 1.6), "green", (0.0, 100.0)),
        compositeChannel(CUSTOM_RANGE, (2.0, 3.0), "cyan", (1.0, 99.0)),
    ]
    assert specs[3] == [compositeChannel("Fe", (6.2, 6.5), "white", (0.0, 100.0))]


def test_channel_specs_fall_back_to_defaults_for_missing_controls():
    ids = [{"type": "x", "index": "0-1"}]
    specs = ci.channel_specs_from_states(["Fe"], ids, [[6.2, 6.5]], ids, [], [], [], [])
    assert specs[0] == [compositeChannel("Fe", (6.2, 6.5), "green")]


def test_get_composite_im_builds_an_image_panel():
    md = combined_metadata()
    channels = [
        compositeChannel("Mg", (1.1, 1.3), "red"),
        compositeChannel("Al", (1.4, 1.6), "green"),
        compositeChannel(CHANNEL_OFF, (0.0, 0.0), "blue"),
    ]
    arrays = [np.array([[0, 10], [0, 0]]), np.array([[0, 0], [0, 10]])]
    fig = ci.get_composite_im(
        channels,
        arrays,
        md,
        scalebar_handler=scalebarHandler(),
        view={"dragmode": "zoom"},
    )

    image, scalebar = fig.data
    assert image.type == "image"
    assert image.source.startswith("data:image/png;base64,")
    assert image.hovertemplate.startswith("Mg (red): %{z[0]}<br>Al (green)")
    assert scalebar.type == "scatter"
    assert fig.layout.dragmode == "zoom"
    assert fig.layout.xaxis.constrain == "range"
    assert fig.layout.yaxis.autorange == "reversed"


def test_get_composite_im_with_nothing_active_is_black():
    md = combined_metadata()
    fig = ci.get_composite_im(
        [compositeChannel(CHANNEL_OFF, (0.0, 0.0), "red")], [], md
    )
    assert fig.data[0].type == "image"
    assert fig.data[0].hovertemplate.startswith("red: %{z[0]}")

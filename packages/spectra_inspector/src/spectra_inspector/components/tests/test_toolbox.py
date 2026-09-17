import dash_bootstrap_components as dbc
import pytest
from dash import html

from spectra_inspector.components.toolbox import (
    CHEVRON_CLOSED,
    PAN,
    RESET_EXTENT,
    ZOOM,
    ZOOM_FACTORS,
    ZOOM_IN,
    ZOOM_OUT,
    icon_button,
    toolbox_card,
    toolbox_collapse,
    toolboxRow,
    toolboxSpec,
)

VIEW_GROUPS = ((ZOOM.id, PAN.id), (ZOOM_IN.id, ZOOM_OUT.id, RESET_EXTENT.id))


def _spec(**overrides) -> toolboxSpec:
    fields = {
        "id_type_base": "demo-toolbox",
        "title": "Demo",
        "tools": (ZOOM, PAN),
        "actions": (ZOOM_IN, ZOOM_OUT),
        "plain": (RESET_EXTENT,),
        "rows": (toolboxRow("View", "tip", VIEW_GROUPS), toolboxRow("Extras", "tip 2")),
        "default_tool": ZOOM.id,
    }
    fields.update(overrides)
    return toolboxSpec(**fields)


def find(component, predicate, found=None):
    found = [] if found is None else found
    if predicate(component):
        found.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, list):
        for child in children:
            find(child, predicate, found)
    elif children is not None and not isinstance(children, str):
        find(children, predicate, found)
    return found


def rows_of(card):
    return find(card, lambda c: isinstance(c, html.Div) and "flex-wrap" in c.className)


def test_ids():
    ids = _spec().ids
    for prop in ids.prop_names:
        assert prop in getattr(ids, prop)
    assert ids.button_id(ZOOM.id) == {"type": "demo-toolbox-tool", "index": "zoom"}
    assert ids.button_id(ZOOM_IN.id) == {
        "type": "demo-toolbox-action",
        "index": "zoomin",
    }
    assert ids.button_id(RESET_EXTENT.id) == "demo-toolbox-reset"
    assert ids.row_id(1) == {"type": "demo-toolbox-row", "index": 1}


def test_rows_are_validated_at_construction():
    with pytest.raises(ValueError, match="unknown"):
        _spec(rows=(toolboxRow("View", "tip", (("zoom", "pan", "nope"),)),))
    with pytest.raises(ValueError, match="exactly one row"):
        _spec(rows=(toolboxRow("View", "tip", (("zoom",),)),))
    with pytest.raises(ValueError, match="exactly one row"):
        _spec(rows=(toolboxRow("View", "tip", (("zoom", "zoom", "pan"),)),))
    with pytest.raises(ValueError, match="default tool"):
        _spec(default_tool="drawrect")
    # a plain button may sit in a row or not
    _spec(
        plain=(RESET_EXTENT,),
        rows=(toolboxRow("View", "tip", (VIEW_GROUPS[0], VIEW_GROUPS[1][:2])),),
    )


def test_active_tool_follows_a_view_store():
    spec = _spec()
    assert spec.active_tool(None) == ZOOM.id
    assert spec.active_tool({"dragmode": None}) == ZOOM.id
    assert spec.active_tool({"dragmode": "pan"}) == "pan"
    assert spec.tool_button_states({"dragmode": "pan"}) == [False, True]
    # a dragmode no button owns presses nothing
    assert not any(spec.tool_button_states({"dragmode": "select"}))
    reported = [{"index": "pan"}, {"index": "zoom"}, {"index": "drawrect"}]
    assert spec.tool_states_for({"dragmode": "pan"}, reported) == [True, False, False]


def test_card_has_labelled_rows_groups_and_extras():
    spec = _spec()
    ids = spec.ids
    extra = html.Span("switch", id="extra")
    card = toolbox_card(spec, extras={1: [extra]})
    assert "si-toolbox" in card.className
    assert card.id == ids.div
    headers = find(card, lambda c: isinstance(c, dbc.CardHeader))
    assert headers[0].children == "Demo"

    rows = rows_of(card)
    assert len(rows) == 2
    label, *groups = rows[0].children
    assert label.children == "View"
    assert label.id == ids.row_id(0)
    assert [[b.id for b in g.children] for g in groups] == [
        [ids.button_id(b) for b in group] for group in VIEW_GROUPS
    ]
    assert rows[1].children[0].children == "Extras"
    assert rows[1].children[1] is extra

    buttons = find(card, lambda c: isinstance(c, dbc.Button))
    pressed = [b.id for b in buttons if b.active]
    assert pressed == [ids.tool_id(ZOOM.id)]
    tooltips = find(card, lambda c: isinstance(c, dbc.Tooltip))
    expected = [b.id for b in buttons] + [ids.row_id(i) for i in range(2)]
    assert sorted(map(str, (t.target for t in tooltips))) == sorted(map(str, expected))
    assert {t.trigger for t in tooltips} == {"hover"}


def test_icon_button_takes_extra_classes_and_props():
    button = icon_button(_spec(), RESET_EXTENT.id, size="sm", class_name="ms-auto")
    assert button.id == "demo-toolbox-reset"
    assert "ms-auto" in button.className
    assert button.size == "sm"
    assert button.children[1] == RESET_EXTENT.label


def test_collapse_starts_closed_with_a_chevron():
    spec = _spec()
    toggle, collapse = toolbox_collapse(spec, toolbox_card(spec), "Tools")
    assert collapse.is_open is False
    assert collapse.id == spec.ids.collapse
    assert toggle.id == spec.ids.toggle
    # the CSS hook that keeps its label readable, like the card's buttons
    assert "si-toolbox-toggle" in toggle.className
    chevron, label = toggle.children
    assert chevron.id == spec.ids.chevron
    assert chevron.className == CHEVRON_CLOSED
    assert label == "Tools"


def test_zoom_factors_match_plotly():
    assert {ZOOM_IN.id: 0.5, ZOOM_OUT.id: 2.0} == ZOOM_FACTORS

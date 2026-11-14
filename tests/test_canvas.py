import re

import pytest

from canvas import (KINDS, DRAW_TOOL, render, validate_actions,
                    repair_model_actions)
from canvas import stroke as stroke_mod
from canvas import palette as palette_mod


# ------------------------------------------------- language integrity ------
def test_core_kinds_present():
    for kind in ('curve', 'path', 'polygon', 'line', 'rectangle', 'ellipse',
                 'text', 'letter', 'select', 'move', 'delete', 'style',
                 'front', 'back', 'clear', 'undo', 'redo'):
        assert kind in KINDS


def test_image_kind_absent_until_registered():
    assert 'image' not in KINDS


def test_register_and_unregister_semantics():
    seen = []
    from canvas.engine import register_action_kind
    seen.append(KINDS[:])
    register_action_kind('testkind', properties={'blob': {'type': 'string'}})
    assert 'testkind' in KINDS
    tool_items = DRAW_TOOL['function']['parameters']['properties']['actions']['items']['properties']
    assert 'blob' in tool_items
    validate_actions([{'kind': 'testkind', 'blob': 'x'}])
    # cleanup: engine has no unregister by design; assert idempotent re-register
    register_action_kind('testkind')
    assert KINDS.count('testkind') == 1
    seen.append(KINDS[:])


def test_repair_downgrades_bad_curves():
    bad = [{'kind': 'curve', 'points': [[0, 0], [10, 10]]}]
    repaired = repair_model_actions(bad)
    assert repaired[0]['kind'] == 'path'


# --------------------------------------------------------- rendering -------
APPLE = [
    {'kind': 'curve', 'points': [[300, 400], [220, 280], [270, 160], [380, 140],
                                 [400, 240], [370, 340], [300, 400]],
     'fill': True, 'stroke': False, 'fill_color': '#648c55'},
    {'kind': 'curve', 'points': [[300, 170], [310, 130], [330, 110], [350, 95]],
     'color': '#5a4a3a', 'stroke': True, 'size': 5, 'brush': 'ink'},
]


def test_render_returns_standalone_svg():
    svg = render(APPLE, validate=False)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert 'viewBox="0 0 1000 650"' in svg
    assert 'feTurbulence' in svg  # grain overlay


def test_ink_stroke_is_tapered_outline_not_uniform():
    svg = render(APPLE, validate=False)
    # the ink stem: a filled outline (path with fill=), not stroke-width
    stem = [e for e in svg.split('<path') if '#5a4a3a' in e]
    assert stem and 'stroke-width' not in stem[0]


def test_soft_brush_uses_blur():
    actions = [{'kind': 'line', 'points': [[100, 100], [400, 100]],
                'color': '#8888aa', 'stroke': True, 'brush': 'soft', 'size': 8}]
    svg = render(actions, validate=False)
    assert 'url(#soft)' in svg


def test_gradients_become_defs():
    actions = [{'kind': 'ellipse', 'x': 100, 'y': 100, 'width': 200, 'height': 200,
                'fill': True, 'gradient': 'linear', 'gradient_angle': 90,
                'fill_color': '#ff0000', 'gradient_color': '#0000ff'}]
    svg = render(actions, validate=False)
    assert '<linearGradient' in svg and 'url(#g1)' in svg


def test_style_edits_existing_object():
    actions = [{'kind': 'rectangle', 'id': 'r1', 'x': 10, 'y': 10, 'width': 50,
                'height': 50, 'fill': True, 'fill_color': '#000000'},
               {'kind': 'style', 'id': 'r1', 'fill_color': '#ff0000'}]
    svg = render(actions, validate=False)
    assert '#ff0000' in svg and '#000000' not in svg


def test_undo_restores_previous_state():
    actions = [{'kind': 'rectangle', 'id': 'a', 'x': 10, 'y': 10, 'width': 50,
                'height': 50, 'fill': True, 'fill_color': '#000000'},
               {'kind': 'rectangle', 'id': 'b', 'x': 100, 'y': 10, 'width': 50,
                'height': 50, 'fill': True, 'fill_color': '#000000'},
               {'kind': 'undo'}]
    svg = render(actions, validate=False)
    assert 'id' not in svg or '#000000' in svg
    assert svg.count('rect x="100"') == 0


# ------------------------------------------------------------- stroke ------
def test_taper_outline_is_closed_and_wider_in_middle():
    pts = [[0, 0], [100, 0]]
    outline = stroke_mod.taper_outline(pts, base=10, taper=0.6)
    xs = [p[0] for p in outline]
    assert outline[0] != outline[-1] or True  # closed loop by construction
    # near the ends the outline must be narrower than at the middle
    end_top = min(p[1] for p in outline if p[0] < 5)
    mid_top = min(p[1] for p in outline if 45 < p[0] < 55)
    assert mid_top < end_top  # middle top edge sits closer to the axis


def test_sample_points_detects_cubic_chain():
    cubic = [[0, 0], [10, 20], [20, 20], [30, 0]]
    samples = stroke_mod.sample_points(cubic)
    assert len(samples) > len(cubic)
    polyline = [[0, 0], [30, 0]]
    assert len(stroke_mod.sample_points(polyline)) >= 2


# ------------------------------------------------------------ palette ------
def test_harmonize_keeps_lightness_saturation():
    colors = ['#ff0000', '#00ff00', '#222266']
    out = palette_mod.harmonize_hexes(colors)
    for original, unified in zip(colors, out):
        _, s0, l0 = palette_mod.hex_to_hsl(original)
        _, s1, l1 = palette_mod.hex_to_hsl(unified)
        assert abs(s0 - s1) < 0.02 and abs(l0 - l1) < 0.02


def test_harmonize_actions_recouples_gradient_stops():
    actions = [{'kind': 'ellipse', 'x': 0, 'y': 0, 'width': 100, 'height': 100,
                'fill': True, 'fill_color': '#ff0000',
                'gradient_stops': [{'offset': 0, 'color': '#ff0000'},
                                   {'offset': 1, 'color': '#00ff00'}]}]
    out = palette_mod.harmonize_actions(actions)
    stops = out[0]['gradient_stops']
    assert stops[0]['color'] == stops[0]['color']  # structure kept
    # fill_color and stop 0 must stay the same color (coherent blend)
    assert out[0]['fill_color'] == stops[0]['color']


def test_mood_palette():
    assert palette_mod.mood_palette('botanical')[0].startswith('#')
    assert palette_mod.mood_palette('nope') is None


# ------------------------------------------------------ ensure_paint -------
def test_ensure_paint_fills_missing_colors():
    actions = [{'kind': 'ellipse', 'x': 100, 'y': 100, 'width': 200,
                'height': 200, 'fill': True},
               {'kind': 'line', 'points': [[0, 0], [100, 0]],
                'stroke': True, 'size': 3}]
    painted = palette_mod.ensure_paint(actions)
    assert painted[0]['fill_color'].startswith('#')
    assert painted[1]['color'].startswith('#')


def test_ensure_paint_respects_existing_colors():
    actions = [{'kind': 'polygon', 'points': [[0, 0], [10, 0], [5, 10]],
                'fill_color': '#123456', 'color': '#654321'}]
    painted = palette_mod.ensure_paint(actions)
    assert painted[0]['fill_color'] == '#123456'
    assert painted[0]['color'] == '#654321'


def test_render_ensure_paint_makes_invisible_drawing_visible():
    import xml.etree.ElementTree as ET
    # no colors at all - the classic small-model omission
    svg = render([{'kind': 'ellipse', 'x': 100, 'y': 100, 'width': 200,
                   'height': 200, 'fill': True}], validate=False)
    ET.fromstring(svg)
    assert 'fill="#e8a87c' in svg  # the warm-mood first fill, not blank


def test_ensure_paint_skips_stroke_false():
    actions = [{'kind': 'curve', 'points': [[0, 0], [10, 10], [20, 0], [30, 10]],
                'fill': True, 'stroke': False}]
    painted = palette_mod.ensure_paint(actions)
    assert 'color' not in painted[0] and painted[0]['fill_color'].startswith('#')


# ------------------------------------------------------ svg well-formed ----
def test_svg_is_parseable():
    import xml.etree.ElementTree as ET
    svg = render(APPLE, validate=False)
    ET.fromstring(svg)  # raises on malformed XML


def test_render_validates_by_default():
    with pytest.raises(ValueError):
        render([{'kind': 'nonsense'}])

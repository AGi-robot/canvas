"""Palette discipline: unified hue relationships make drawings read as art.

LLMs pick colors one object at a time, which drifts into muddy or clashing
palettes.  `harmonize_actions` anchors on the first dominant color and maps
every other distinct hue onto a fixed, pleasing spread around it while
keeping each color's own saturation and lightness - relationships (darker,
cooler, softer) survive, chaos does not.
"""
import colorsys

# Hue offsets (degrees) distributed around the anchor hue.  Small offsets keep
# a unified analogous feel; the two large offsets allow a restrained accent
# pair.  Order matters: it maps sorted distinct hues, darkest relationship
# first.
SPREADS = {
    'analogous': (0, 14, -14, 28, -28, 42, -42, 56),
    'balanced':  (0, 18, -18, 36, -36, 150, -150, 200),
    'complementary': (0, 12, -12, 24, 180, 168, 192, 150),
}

# A few curated palettes for mood-based starts (fill colors).
MOODS = {
    'warm':      ('#e8a87c', '#d97862', '#f2d5a0', '#8c5a48', '#423731'),
    'cool':      ('#7ca8c9', '#5b7fa6', '#a3c4d9', '#46608c', '#2c3550'),
    'botanical': ('#648c55', '#4a6b3a', '#8fb573', '#c9d8a8', '#5a4a3a'),
    'pastel':    ('#c9a3c9', '#a3b8c9', '#c9c3a3', '#b8a3c9', '#e0d5e0'),
    'jewel':     ('#2c6b5a', '#8c3a5a', '#3a5a8c', '#c9a03a', '#42304a'),
}


def hex_to_hsl(hex_color):
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, l


def hsl_to_hex(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l, s)
    return '#{:02x}{:02x}{:02x}'.format(round(r * 255), round(g * 255), round(b * 255))


def harmonize_hexes(hex_colors, scheme='balanced'):
    """Map distinct hues of a palette onto a fixed spread around the anchor."""
    if not hex_colors:
        return []
    spread = SPREADS.get(scheme, SPREADS['balanced'])
    hsls = [hex_to_hsl(c) for c in hex_colors]
    anchor = hsls[0][0]
    # order distinct hues by hue distance from anchor to map stably
    order = sorted(range(len(hsls)), key=lambda i: min(abs(hsls[i][0] - anchor),
                                                       360 - abs(hsls[i][0] - anchor)))
    offset_of = {}
    for rank, i in enumerate(order):
        offset_of[i] = spread[min(rank, len(spread) - 1)]
    return [hsl_to_hex(anchor + offset_of[i], s, l)
            for i, (_, s, l) in enumerate(hsls)]


def harmonize_actions(actions, scheme='balanced'):
    """Recolor an action list in place-ish: returns a new action list.

    Only objects' paint colors are touched; geometry, opacity and gradients'
    structure stay as authored.  Gradient stop colors participate so a shape's
    internal blend stays coherent with the rest.
    """
    distinct = []
    for action in actions:
        for key in ('color', 'fill_color', 'gradient_color'):
            value = action.get(key)
            if value and value not in distinct:
                distinct.append(value)
        for stop in action.get('gradient_stops') or []:
            if stop.get('color') and stop['color'] not in distinct:
                distinct.append(stop['color'])
    if len(distinct) < 2:
        return actions
    mapping = dict(zip(distinct, harmonize_hexes(distinct, scheme)))
    out = []
    for action in actions:
        action = dict(action)
        for key in ('color', 'fill_color', 'gradient_color'):
            if action.get(key) in mapping:
                action[key] = mapping[action[key]]
        if action.get('gradient_stops'):
            action['gradient_stops'] = [{**stop, 'color': mapping.get(stop['color'], stop['color'])}
                                        for stop in action['gradient_stops']]
        out.append(action)
    return out


def ensure_paint(actions, mood='warm'):
    """Guarantee visible paint: fill missing fill_color/color from a mood palette.

    Small models often omit colors entirely, which renders as nothing.  This
    is the renderer's beauty floor: an unfilled shape still becomes a finished
    colored mass, cycled through the mood palette in draw order.
    """
    colors = MOODS.get(mood, MOODS['warm'])
    out = []
    index = 0
    for action in actions:
        action = dict(action)
        kind = action.get('kind')
        if kind in ('curve', 'path', 'polygon', 'line', 'rectangle', 'ellipse', 'text', 'letter'):
            wants_fill = action.get('fill', kind == 'polygon') or kind in ('rectangle', 'ellipse')
            if wants_fill and not action.get('fill_color'):
                action['fill_color'] = colors[index % len(colors)]
                index += 1
            wants_outline = (action.get('stroke') is not False
                             and ('points' in action or kind in ('rectangle', 'ellipse', 'text')))
            if wants_outline and not action.get('color'):
                action['color'] = colors[(index + 2) % len(colors)]
        out.append(action)
    return out


def mood_palette(mood):
    """A starting palette for a mood, or None for unknown moods."""
    return MOODS.get((mood or '').strip().lower())

"""Render the canvas action language to SVG.

`render(actions)` replays an action list (the same replay semantics as the
browser Canvas page: move/delete/style/front/back/clear/undo/redo) and emits
a standalone SVG string with painterly treatment:

* ink brush strokes become pressure-tapered filled outlines (`canvas.stroke`)
* soft brush strokes get a gaussian-blur filter (airbrush shading)
* marker strokes stay constant-width and translucent
* gradients, opacity and smooth rounding follow the language spec
* an optional feTurbulence grain overlay gives the page a paper feel

The renderer is deterministic: same actions, same SVG.
"""
import math
import re

from .engine import KINDS
from . import stroke as _stroke

HEX_RE = re.compile(r'#[0-9a-fA-F]{6}')
W, H = 1000, 650
_FONT_STACKS = {
    'sans': 'sans-serif',
    'serif': 'Georgia, serif',
    'mono': 'ui-monospace, monospace',
    'handwritten': 'Segoe Script, Comic Sans MS, cursive',
}


def _fmt(value):
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip('0').rstrip('.')
        return text or '0'
    return str(value)


def _path_from_points(points, kind, smooth):
    """SVG path data for curve/path/polygon/line point lists."""
    pts = [(float(x), float(y)) for x, y in points]
    if kind == 'curve' and len(pts) >= 4 and (len(pts) - 1) % 3 == 0:
        d = f"M {_fmt(pts[0][0])} {_fmt(pts[0][1])}"
        for i in range(1, len(pts) - 2, 3):
            d += (f" C {_fmt(pts[i][0])} {_fmt(pts[i][1])} {_fmt(pts[i+1][0])}"
                  f" {_fmt(pts[i+1][1])} {_fmt(pts[i+2][0])} {_fmt(pts[i+2][1])}")
        return d
    if kind == 'line':
        return f"M {_fmt(pts[0][0])} {_fmt(pts[0][1])} L {_fmt(pts[-1][0])} {_fmt(pts[-1][1])}"
    closed = kind == 'polygon'
    if smooth and len(pts) > 2:
        # quadratic midpoint rounding through interior points
        d = f"M {_fmt(pts[0][0])} {_fmt(pts[0][1])}"
        for i in range(1, len(pts) - 1):
            mx = (pts[i][0] + pts[i + 1][0]) / 2
            my = (pts[i][1] + pts[i + 1][1]) / 2
            d += f" Q {_fmt(pts[i][0])} {_fmt(pts[i][1])} {_fmt(mx)} {_fmt(my)}"
        d += f" L {_fmt(pts[-1][0])} {_fmt(pts[-1][1])}"
    else:
        d = "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in pts)
    return d + (" Z" if closed else "")


class Renderer:
    """Replays actions onto an ordered object list, then emits SVG."""

    def __init__(self, background='#ffffff'):
        self.background = background
        self.objects = []      # ordered list of normalized action dicts
        self._undo = []
        self._redo = []

    # ------------------------------------------------------------- state --
    def _snapshot(self):
        import copy
        self._undo.append(copy.deepcopy(self.objects))
        self._redo.clear()

    def _find(self, object_id):
        for index, obj in enumerate(self.objects):
            if obj.get('id') == object_id:
                return index
        return None

    def apply(self, action):
        kind = action['kind']
        if kind in ('undo', 'redo', 'select'):
            if kind == 'undo':
                if self._undo:
                    self._redo.append(self.objects)
                    self.objects = self._undo.pop()
            else:
                if self._redo:
                    self._undo.append(self.objects)
                    self.objects = self._redo.pop()
            return
        if kind == 'clear':
            self._snapshot()
            self.objects = []
            return
        if kind == 'back':
            self._snapshot()
            index = self._find(action.get('id'))
            if index:
                self.objects.insert(0, self.objects.pop(index))
            return
        if kind == 'front':
            self._snapshot()
            index = self._find(action.get('id'))
            if index is not None:
                self.objects.append(self.objects.pop(index))
            return
        if kind == 'delete':
            self._snapshot()
            index = self._find(action.get('id'))
            if index is not None:
                self.objects.pop(index)
            return
        if kind == 'move':
            self._snapshot()
            index = self._find(action.get('id'))
            if index is not None:
                obj = self.objects[index]
                dx, dy = float(action.get('dx', 0)), float(action.get('dy', 0))
                if 'points' in obj:
                    obj['points'] = [[x + dx, y + dy] for x, y in obj['points']]
                for key in ('x', 'y'):
                    if key in obj:
                        obj[key] = max(0, obj[key] + (dx if key == 'x' else dy))
            return
        if kind == 'style':
            index = self._find(action.get('id'))
            if index is not None:
                self._snapshot()
                paint = {k: v for k, v in action.items() if k in (
                    'color', 'fill_color', 'gradient_color', 'gradient',
                    'gradient_angle', 'gradient_stops', 'opacity', 'size',
                    'brush', 'font', 'stroke', 'fill', 'text')}
                self.objects[index].update(paint)
            return
        if kind == 'erase':
            self._snapshot()
            self.objects.append({**action, 'fill_color': self.background,
                                 'fill': True, 'stroke': False})
            return
        # a new drawn object
        self._snapshot()
        self.objects.append(dict(action))

    # -------------------------------------------------------------- svg  --
    def _defs(self):
        defs, gid = [], 0
        for obj in self.objects:
            gradient = obj.get('gradient', 'none')
            if gradient == 'none':
                continue
            gid += 1
            obj['_grad_id'] = f"g{gid}"
            stops = obj.get('gradient_stops') or [
                {'offset': 0, 'color': obj.get('fill_color', '#cccccc')},
                {'offset': 1, 'color': obj.get('gradient_color', obj.get('fill_color', '#cccccc'))}]
            angle = float(obj.get('gradient_angle', 0)) * math.pi / 180
            x2, y2 = round(math.cos(angle), 3), round(math.sin(angle), 3)
            x1, y1 = round(1 - max(0, x2) - min(0, x2), 3) or 0, 0
            x1, y1 = -x2, -y2  # gradient runs along the angle vector
            stop_tags = ''.join(
                f'<stop offset="{_fmt(s.get("offset", i / (len(stops) - 1)))}" stop-color="{s["color"]}"/>'
                for i, s in enumerate(stops))
            if gradient == 'linear':
                defs.append(f'<linearGradient id="{obj["_grad_id"]}" x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}">{stop_tags}</linearGradient>')
            else:
                defs.append(f'<radialGradient id="{obj["_grad_id"]}" cx="50%" cy="50%" r="75%">{stop_tags}</radialGradient>')
        blur = '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6"/></filter>'
        grain = ('<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/>'
                 '<feColorMatrix type="saturate" values="0"/></filter>')
        return '<defs>' + ''.join(defs) + blur + grain + '</defs>'

    def _paint(self, obj):
        fill = obj.get('fill', obj['kind'] == 'polygon')
        fill_color = obj.get('fill_color') if fill else 'none'
        opacity = _fmt(float(obj.get('opacity', 1)))
        stroke_color = obj.get('color') if obj.get('stroke') is not False else None
        return fill, fill_color, opacity, stroke_color

    def _stroke_element(self, obj, d):
        """Emit the outline of a stroked open path according to its brush."""
        brush = obj.get('brush', 'ink')
        size = max(1.0, float(obj.get('size', 6)))
        color = obj.get('color', '#333333')
        if brush == 'ink' and obj['kind'] in ('curve', 'path', 'line'):
            outline = _stroke.taper_outline(obj['points'], base=size)
            od = _path_from_points(outline, 'polygon', False)
            return f'<path d="{od}" fill="{color}" fill-opacity="0.92" stroke="none"/>'
        if brush == 'soft':
            width = _fmt(size * 2.2)
            return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"'
                    f' stroke-linecap="round" stroke-opacity="0.35" filter="url(#soft)"/>')
        return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{_fmt(size)}"'
                f' stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.8"/>')

    def _object_svg(self, obj):
        kind = obj['kind']
        fill, fill_color, opacity, stroke_color = self._paint(obj)
        parts = []
        gid = obj.get('_grad_id')
        fill_attr = f'fill="url(#{gid})"' if (fill and gid) else f'fill="{fill_color}"'
        if kind in ('curve', 'path', 'polygon', 'line'):
            d = _path_from_points(obj['points'], kind, obj.get('smooth', False))
            parts.append(f'<path d="{d}" {fill_attr} opacity="{opacity}" fill-rule="evenodd"/>')
            if stroke_color:
                parts.append(self._stroke_element(obj, d))
        elif kind in ('rectangle', 'ellipse'):
            x, y = float(obj.get('x', 0)), float(obj.get('y', 0))
            w, h = float(obj.get('width', 0)), float(obj.get('height', 0))
            if kind == 'rectangle':
                shape = f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}"'
            else:
                shape = f'<ellipse cx="{_fmt(x + w / 2)}" cy="{_fmt(y + h / 2)}" rx="{_fmt(w / 2)}" ry="{_fmt(h / 2)}"'
            parts.append(f'{shape} {fill_attr} opacity="{opacity}"/>')
            if stroke_color:
                sw = max(1.0, float(obj.get('size', 4)))
                parts.append(f'{shape} fill="none" stroke="{stroke_color}" stroke-width="{_fmt(sw)}"/>')
        elif kind == 'text':
            font = _FONT_STACKS[obj.get('font', 'sans')]
            parts.append(f'<text x="{_fmt(obj.get("x", 0))}" y="{_fmt(obj.get("y", 0) + float(obj.get("size", 24)) * 0.8)}"'
                         f' font-family="{font}" font-size="{_fmt(obj.get("size", 24))}"'
                         f' fill="{obj.get("color", "#333333")}" opacity="{opacity}">'
                         f'{_esc(obj.get("text", ""))}</text>')
        elif kind == 'letter':
            page_x, page_y = float(obj.get('x', 270)), float(obj.get('y', 20))
            pw, ph = float(obj.get('width', 460)), float(obj.get('height', 610))
            margin = float(obj.get('margin', 40))
            line_height = float(obj.get('line_height', 1.5))
            size = float(obj.get('size', 20))
            font = _FONT_STACKS[obj.get('font', 'serif')]
            color = obj.get('color', '#333333')
            align = {'left': 'start', 'center': 'middle', 'right': 'end'}[obj.get('align', 'left')]
            tx = page_x + margin if align == 'start' else page_x + pw / 2 if align == 'middle' else page_x + pw - margin
            parts.append(f'<rect x="{_fmt(page_x)}" y="{_fmt(page_y)}" width="{_fmt(pw)}" height="{_fmt(ph)}" fill="#fffdf5" stroke="#d8d4c8"/>')
            for i, line in enumerate(str(obj.get('text', '')).split('\n')):
                ty = page_y + margin + size * 0.8 + i * size * line_height
                parts.append(f'<text x="{_fmt(tx)}" y="{_fmt(ty)}" text-anchor="{align}" font-family="{font}" font-size="{_fmt(size)}" fill="{color}">{_esc(line)}</text>')
        elif kind == 'image':
            png = obj.get('png_b64') or obj.get('_png_b64')
            x, y = float(obj.get('x', 0)), float(obj.get('y', 0))
            w, h = float(obj.get('width', 500)), float(obj.get('height', 400))
            if png:
                parts.append(f'<image x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" href="data:image/png;base64,{png}"/>')
            else:
                parts.append(f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" fill="#ece9e4" stroke="#b8b4ac" stroke-dasharray="8 6"/>')
        return ''.join(parts)

    def to_svg(self, grain=True):
        defs = self._defs()
        body = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="{self.background}"/>']
        for obj in self.objects:
            body.append(self._object_svg(obj))
        if grain:
            body.append(f'<rect x="0" y="0" width="{W}" height="{H}" filter="url(#grain)" opacity="0.05"/>')
        for obj in self.objects:
            obj.pop('_grad_id', None)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
                f'width="{W}" height="{H}">{defs}{"".join(body)}</svg>')


def _esc(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def render(actions, *, grain=True, validate=True, ensure_paint=True):
    """Validate (default) then replay an action list into an SVG string.

    ensure_paint: fill missing colors from a mood palette so nothing renders
    as invisible - the renderer's beauty floor (`canvas.palette`).
    """
    if validate:
        from .engine import validate_actions
        actions = validate_actions(actions)
    if ensure_paint:
        from .palette import ensure_paint
        actions = ensure_paint(actions)
    renderer = Renderer()
    for action in actions:
        renderer.apply(action)
    return renderer.to_svg(grain=grain)

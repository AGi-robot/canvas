"""Stroke dynamics: the difference between a line and a drawn line.

Uniform-width strokes read as machine output. Real drawing tools - ink brush,
pencil, marker - modulate width along the stroke: pressure taper at the ends,
a slightly swelling body. This module turns an action's points into a filled
outline polygon with that width profile, which the SVG emitter renders as a
closed path instead of a uniform stroke.
"""
import math

# Number of samples per curve segment / per polyline span.
SAMPLES_PER_SPAN = 14


def _cubic(p0, p1, p2, p3, t):
    u = 1.0 - t
    x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
    return x, y


def _finite(points):
    return all(math.isfinite(x) and math.isfinite(y) for x, y in points)


def sample_points(points):
    """Dense samples along a point list.

    Accepts either a cubic chain (start + 3n points, as the engine's 'curve')
    or a plain polyline (engine's 'path'/'line').  Detection: cubic chains
    have 1 + 3n points.
    """
    points = [(float(x), float(y)) for x, y in points]
    if len(points) >= 4 and (len(points) - 1) % 3 == 0:
        samples = [points[0]]
        for i in range(1, len(points) - 2, 3):
            p0, p1, p2, p3 = points[i - 1], points[i], points[i + 1], points[i + 2]
            for s in range(1, SAMPLES_PER_SPAN + 1):
                samples.append(_cubic(p0, p1, p2, p3, s / SAMPLES_PER_SPAN))
        return samples
    # polyline: resample each span
    samples = []
    for i in range(len(points) - 1):
        (x0, y0), (x1, y1) = points[i], points[i + 1]
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(2, int(length / 8) + 1)
        for s in range(n):
            samples.append((x0 + (x1 - x0) * s / n, y0 + (y1 - y0) * s / n))
    samples.append(points[-1])
    return samples if _finite(samples) else points


def _width_envelope(t, base, taper, pressure=0.8):
    """Width at relative position t in [0,1].

    taper=0 -> constant width (a marker); taper=1 -> a needle that only marks
    at the middle.  `pressure` shapes how fast the brush fills (higher = the
    stroke swells faster after a light entry).
    """
    if taper <= 0:
        return base
    bell = math.sin(math.pi * t) ** pressure
    return base * (taper + (1.0 - taper) * bell)


def taper_outline(points, base=6.0, taper=0.55, pressure=0.8):
    """Build a closed outline polygon around a stroke with a width profile.

    Returns a list of [x, y] closing back on the start, suitable as a filled
    SVG path.  Falls back to the input points when degenerate.
    """
    samples = sample_points(points)
    if len(samples) < 2 or base <= 0:
        return [[x, y] for x, y in samples]

    # cumulative length for relative position
    lengths = [0.0]
    for (x0, y0), (x1, y1) in zip(samples, samples[1:]):
        lengths.append(lengths[-1] + math.hypot(x1 - x0, y1 - y0))
    total = lengths[-1]
    if total <= 0:
        return [[x, y] for x, y in samples]

    left, right = [], []
    for i, (x, y) in enumerate(samples):
        t = lengths[i] / total
        w = _width_envelope(t, base, taper, pressure)
        # tangent via neighbours
        if i == 0:
            dx, dy = samples[1][0] - x, samples[1][1] - y
        elif i == len(samples) - 1:
            dx, dy = x - samples[-2][0], y - samples[-2][1]
        else:
            dx, dy = samples[i + 1][0] - samples[i - 1][0], samples[i + 1][1] - samples[i - 1][1]
        norm = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / norm, dx / norm
        left.append((x + nx * w / 2, y + ny * w / 2))
        right.append((x - nx * w / 2, y - ny * w / 2))

    outline = [(round(x, 2), round(y, 2)) for x, y in left + right[::-1]]
    return [[x, y] for x, y in outline]

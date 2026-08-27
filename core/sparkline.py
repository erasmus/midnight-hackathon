"""Trajectory sparkline (issue #33).

Inline SVG rather than matplotlib. The dossier must be a *self-contained* HTML
file (#32), and an inline `<svg>` needs no dependency, no image encoding and no
external request -- it also scales cleanly and follows the surrounding text
colour, so it works in a light or dark viewer.

Degrades to an empty string whenever there is nothing honest to draw; the
dossier simply omits the chart in that case.
"""

from __future__ import annotations

WIDTH = 320
HEIGHT = 60
PADDING = 6


def _usable_points(history: list[dict]) -> list[tuple[str, float]]:
    points = [
        (entry.get("date") or "", float(entry["rating"]))
        for entry in history or []
        if entry.get("rating") is not None
    ]
    points.sort(key=lambda item: item[0])
    return points


def sparkline_svg(
    history: list[dict], width: int = WIDTH, height: int = HEIGHT
) -> str:
    """A rating-history sparkline, or `""` when there is no trajectory to show."""
    points = _usable_points(history)
    if len(points) < 2:
        return ""

    ratings = [rating for _, rating in points]
    low, high = min(ratings), max(ratings)
    span = high - low
    inner_height = height - 2 * PADDING
    inner_width = width - 2 * PADDING

    coordinates = []
    for index, rating in enumerate(ratings):
        x = PADDING + inner_width * index / (len(ratings) - 1)
        # A flat history has no span; draw it down the middle rather than
        # dividing by zero.
        fraction = 0.5 if span == 0 else (rating - low) / span
        y = PADDING + inner_height * (1 - fraction)
        coordinates.append(f"{x:.1f},{y:.1f}")

    first_date, _ = points[0]
    last_date, _ = points[-1]

    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="Rating from {low:g} to {high:g}" '
        f'style="overflow:visible">'
        f'<polyline points="{" ".join(coordinates)}" fill="none" '
        f'stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" '
        f'stroke-linecap="round" opacity="0.85"/>'
        f'<circle cx="{coordinates[-1].split(",")[0]}" '
        f'cy="{coordinates[-1].split(",")[1]}" r="2.5" fill="currentColor"/>'
        f'<text x="0" y="{height + 12}" font-size="10" fill="currentColor" '
        f'opacity="0.6">{low:g} · {first_date}</text>'
        f'<text x="{width}" y="{height + 12}" font-size="10" text-anchor="end" '
        f'fill="currentColor" opacity="0.6">{high:g} · {last_date}</text>'
        f"</svg>"
    )

"""Rating-history sparkline as inline SVG (issue #33).

Self-contained HTML cannot depend on a matplotlib PNG sitting next to the
file, so the sparkline is an SVG polyline. Empty history returns None and the
dossier degrades to a one-line caption.
"""

from __future__ import annotations

from typing import Any


def history_points(rating_history: list[Any]) -> list[tuple[str, float]]:
    """Accept both adapter dicts ({date, rating}) and (date, rating) pairs."""
    points: list[tuple[str, float]] = []
    for item in rating_history or []:
        if isinstance(item, dict):
            date = item.get("date")
            rating = item.get("rating")
            if date is None or rating is None:
                continue
            points.append((str(date), float(rating)))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            points.append((str(item[0]), float(item[1])))
    points.sort(key=lambda p: p[0])
    return points


def collect_history(profiles: list[Any]) -> list[tuple[str, float]]:
    points: list[tuple[str, float]] = []
    for profile in profiles:
        points.extend(history_points(getattr(profile, "rating_history", None) or []))
    points.sort(key=lambda p: p[0])
    return points[-80:]


def sparkline_svg(points: list[tuple[str, float]], width: int = 640, height: int = 88) -> str | None:
    if len(points) < 2:
        return None
    vals = [v for _, v in points]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pad = 6.0
    inner_w = width - pad * 2
    inner_h = height - pad * 2
    coords = []
    n = len(vals) - 1
    for i, v in enumerate(vals):
        x = pad + (i / n) * inner_w
        y = pad + (1 - (v - lo) / span) * inner_h
        coords.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(coords)
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Rating history">'
        f'<polyline fill="none" stroke="#9a6b1f" stroke-width="2" points="{polyline}"/>'
        f"</svg>"
    )

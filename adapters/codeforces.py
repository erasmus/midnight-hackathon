"""Codeforces adapter (issue #13).

`api/user.ratedList?activeOnly=true` returns the entire ranked population in a
single call, which gives us *exact* percentiles for free -- no estimation, no
sampling. That one call also carries name / country / organization, so the
separate `user.info` batch the issue mentions is unnecessary: one request is
strictly politer than two.

`api/user.rating?handle=` is per-user, so full contest history is fetched only
for the top slice (`history_for`), keeping us well inside the rate limit.

Consent-by-disclosure: everything here is a public profile field the user
published on their own Codeforces page. No de-anonymisation.
"""

from __future__ import annotations

import bisect
from datetime import datetime, timezone

from core.http import default_client
from core.schema import RawProfile

name = "codeforces"

API = "https://codeforces.com/api"
PROFILE_URL = "https://codeforces.com/profile/{handle}"

# Top-of-tail only (Epic 2 cross-cutting constraint).
MAX_PROFILES = 500
# International Grandmaster territory; the tail we actually care about.
RATING_FLOOR = 2400
# Contest history costs one request per user, so only the sharp end gets it.
DEFAULT_HISTORY_FOR = 50


def _result(client, url):
    payload = client.get_json(url)
    if payload.get("status") != "OK":
        raise RuntimeError(
            f"Codeforces API returned {payload.get('status')}: "
            f"{payload.get('comment', 'no comment')} ({url})"
        )
    return payload["result"]


def _display_name(user: dict) -> str:
    parts = [user.get("firstName"), user.get("lastName")]
    full = " ".join(p for p in parts if p).strip()
    return full or user["handle"]


def _percentiles(users: list[dict]) -> dict[str, float]:
    """Exact percentile per handle, against the full rated population."""
    ratings = sorted(u["rating"] for u in users)
    total = len(ratings)
    return {
        u["handle"]: 100.0 * bisect.bisect_left(ratings, u["rating"]) / total
        for u in users
    }


def _rating_history(client, handle: str) -> list[dict]:
    """Dated contest results. A missing history must not lose the profile."""
    try:
        entries = _result(client, f"{API}/user.rating?handle={handle}")
    except Exception:  # noqa: BLE001 - history is a nice-to-have, not the point
        return []
    return [
        {
            "date": datetime.fromtimestamp(
                e["ratingUpdateTimeSeconds"], tz=timezone.utc
            ).strftime("%Y-%m-%d"),
            "rating": e["newRating"],
            "contest": e.get("contestName"),
            "rank": e.get("rank"),
        }
        for e in entries
    ]


def fetch_top(
    n: int = MAX_PROFILES,
    client=None,
    history_for: int | None = None,
) -> list[RawProfile]:
    client = client or default_client()
    history_for = DEFAULT_HISTORY_FOR if history_for is None else history_for

    population = _result(client, f"{API}/user.ratedList?activeOnly=true")
    population = [u for u in population if u.get("rating") is not None]
    percentile = _percentiles(population)

    ranked = sorted(
        (u for u in population if u["rating"] >= RATING_FLOOR),
        key=lambda u: (-u["rating"], u["handle"]),
    )[: min(n, MAX_PROFILES)]

    fetched_at = datetime.now(timezone.utc).isoformat()
    profiles = []
    for i, u in enumerate(ranked):
        handle = u["handle"]
        profiles.append(
            RawProfile(
                platform=name,
                handle=handle,
                display_name=_display_name(u),
                url=PROFILE_URL.format(handle=handle),
                rating=u["rating"],
                rank_pct=percentile[handle],
                rating_history=_rating_history(client, handle) if i < history_for else [],
                country=u.get("country"),
                raw={
                    "organization": u.get("organization"),
                    "maxRating": u.get("maxRating"),
                    "rank": u.get("rank"),
                    "contribution": u.get("contribution"),
                },
                fetched_at=fetched_at,
            )
        )
    return profiles

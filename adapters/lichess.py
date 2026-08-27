"""Lichess adapter (issue #14).

Three leaderboards (`api/player/top/200/{blitz,rapid,classical}`) deduped to
unique players, then one *bulk* `POST /api/users` per 300 handles for bio,
links, title and declared FIDE rating -- 2 requests instead of 600. Contest
history is per-user, so it goes only to the top slice (`history_for`).

`title` and `fideRating` are the join keys the FIDE adapter (#15) and the FIDE
join (#21) rely on, so they are stored verbatim even when empty.

`rank_pct` is deliberately left unset: Lichess exposes only the top 200, so
there is no denominator. Claiming a percentile from a truncated leaderboard
would be a fabrication -- Epic 5 can normalise on rating instead.

Consent-by-disclosure: bio, links, flag and real name are fields the player
chose to publish on their own profile. Nothing here is inferred or unmasked.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from core.http import default_client
from core.schema import RawProfile

name = "lichess"

API = "https://lichess.org/api"
PROFILE_URL = "https://lichess.org/@/{handle}"

TIME_CONTROLS = ("blitz", "rapid", "classical")
LEADERBOARD_SIZE = 200
# Top-of-tail only (Epic 2 cross-cutting constraint).
MAX_PROFILES = 500
# Lichess accepts up to 300 usernames per bulk /api/users call.
BULK_BATCH = 300
DEFAULT_HISTORY_FOR = 50

URL_PATTERN = re.compile(r"https?://[^\s,;)\]]+")


def _leaderboards(client) -> dict[str, dict]:
    """Merge the per-control leaderboards into one player -> data mapping.

    A dead leaderboard costs us that one time control, not the whole adapter.
    """
    players: dict[str, dict] = {}
    for control in TIME_CONTROLS:
        try:
            payload = client.get_json(f"{API}/player/top/{LEADERBOARD_SIZE}/{control}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! lichess {control} leaderboard unavailable: {exc}")
            continue
        for rank, entry in enumerate(payload.get("users", []), start=1):
            handle = entry["username"]
            player = players.setdefault(
                handle, {"handle": handle, "ratings": {}, "top_rank": {}}
            )
            rating = (entry.get("perfs", {}).get(control) or {}).get("rating")
            if rating is not None:
                player["ratings"][control] = rating
            player["top_rank"][control] = rank
    return players


def _details(client, handles: list[str]) -> dict[str, dict]:
    """Bulk-fetch full profiles. A failed batch degrades to leaderboard-only."""
    details: dict[str, dict] = {}
    for start in range(0, len(handles), BULK_BATCH):
        batch = handles[start : start + BULK_BATCH]
        try:
            users = client.post_json(f"{API}/users", ",".join(batch))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! lichess bulk user fetch failed for {len(batch)} handles: {exc}")
            continue
        for user in users or []:
            details[user["username"]] = user
    return details


def _links(profile: dict) -> list[str]:
    """URLs the player published, from the links field and the bio prose."""
    found: list[str] = []
    for field in (profile.get("links"), profile.get("bio")):
        for url in URL_PATTERN.findall(field or ""):
            url = url.rstrip(".,")
            if url not in found:
                found.append(url)
    return found


def _display_name(handle: str, profile: dict) -> str:
    full = " ".join(
        p for p in (profile.get("firstName"), profile.get("lastName")) if p
    ).strip()
    return full or handle


def _rating_history(client, handle: str) -> list[dict]:
    """Dated rating points. The API's month field is 0-indexed."""
    try:
        series = client.get_json(f"{API}/user/{handle}/rating-history")
    except Exception as exc:  # noqa: BLE001 - history is a nice-to-have
        # Logged so a fetch failure stays distinguishable from a genuinely
        # empty history (Lichess returns [] for some accounts).
        print(f"  ! lichess rating history unavailable for {handle}: {exc}")
        return []
    points = []
    for entry in series or []:
        for year, month, day, rating in entry.get("points", []):
            points.append(
                {
                    "date": f"{year:04d}-{month + 1:02d}-{day:02d}",
                    "rating": rating,
                    "control": entry.get("name"),
                }
            )
    points.sort(key=lambda p: p["date"])
    return points


def fetch_top(
    n: int = MAX_PROFILES,
    client=None,
    history_for: int | None = None,
) -> list[RawProfile]:
    client = client or default_client()
    history_for = DEFAULT_HISTORY_FOR if history_for is None else history_for

    players = _leaderboards(client)
    ranked = sorted(
        players.values(),
        key=lambda p: (-max(p["ratings"].values(), default=0), p["handle"]),
    )[: min(n, MAX_PROFILES)]

    details = _details(client, [p["handle"] for p in ranked])
    fetched_at = datetime.now(timezone.utc).isoformat()

    profiles = []
    for i, player in enumerate(ranked):
        handle = player["handle"]
        user = details.get(handle, {})
        profile = user.get("profile") or {}
        profiles.append(
            RawProfile(
                platform=name,
                handle=handle,
                display_name=_display_name(handle, profile),
                url=PROFILE_URL.format(handle=handle),
                rating=max(player["ratings"].values(), default=None),
                rank_pct=None,  # see module docstring
                rating_history=_rating_history(client, handle) if i < history_for else [],
                profile_links=_links(profile),
                country=profile.get("flag"),
                raw={
                    "ratings": player["ratings"],
                    "top_rank": player["top_rank"],
                    # Join keys for the FIDE adapter (#15) and join (#21).
                    "title": user.get("title"),
                    "fide_rating": profile.get("fideRating"),
                    "bio": profile.get("bio"),
                    "created_at": user.get("createdAt"),
                },
                fetched_at=fetched_at,
            )
        )
    return profiles

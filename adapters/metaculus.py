"""Metaculus adapter (issue #16).

The public JSON shape has moved (`/api2/rankings/`, `/api/leaderboards/global/`,
`/api2/users/{id}`). We try known layouts, and if none match — or the API
demands a token we don't have — we log and return [] so the pipeline continues.

Set `METACULUS_TOKEN` (Metaculus account API token) when you have one.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from core.http import HttpClient, HttpError, default_client
from core.schema import RawProfile

name = "metaculus"

SITE = "https://www.metaculus.com"
PROFILE_URL = SITE + "/accounts/profile/{user_id}"
MAX_PROFILES = 200
DEFAULT_DETAIL_FOR = 50

URL_PATTERN = re.compile(r"https?://[^\s,;\"'<>)\]]+")

# Tried in order. First payload we can parse wins.
RANKING_URLS = (
    f"{SITE}/api/leaderboards/global/?limit={{limit}}&score_type=peer",
    f"{SITE}/api/leaderboards/global/?limit={{limit}}",
    f"{SITE}/api2/rankings/?limit={{limit}}",
)

USER_URLS = (
    SITE + "/api2/users/{user_id}/",
    SITE + "/api/users/{user_id}/",
)


def _urls_from_text(*parts: str | None) -> list[str]:
    found: list[str] = []
    for part in parts:
        for url in URL_PATTERN.findall(part or ""):
            url = url.rstrip(").,")
            if url not in found:
                found.append(url)
    return found


def _entries(payload) -> list[dict] | None:
    """Return ranking rows, or None if this JSON is not a shape we know."""
    if not isinstance(payload, dict):
        return None
    for key in ("entries", "results", "users"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows
    return None


def _row_user(row: dict) -> tuple[str | None, str | None, float | None, int | None]:
    """user_id, username, score, rank — all optional."""
    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    user_id = row.get("user_id") or row.get("id") or user.get("id")
    username = (
        row.get("username")
        or user.get("username")
        or row.get("name")
        or user.get("name")
    )
    score = row.get("score") or row.get("peer_score") or user.get("score")
    rank = row.get("rank") or row.get("position")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    try:
        rank_i = int(rank) if rank is not None else None
    except (TypeError, ValueError):
        rank_i = None
    if user_id is None and username is None:
        return None, None, None, None
    return (str(user_id) if user_id is not None else None, username, score_f, rank_i)


def _authed_client(token: str | None, fallback):
    if not token:
        return fallback
    # Don't mutate the process-wide client — a second instance keeps spacing
    # local to Metaculus and leaves GitHub/OpenAlex headers alone.
    extra = HttpClient()
    extra.session.headers["Authorization"] = f"Token {token}"
    extra.session.headers["Accept"] = "application/json"
    return extra


def fetch_top(
    n: int = MAX_PROFILES,
    client=None,
    token: str | None = None,
    detail_for: int | None = None,
) -> list[RawProfile]:
    token = os.environ.get("METACULUS_TOKEN") if token is None else token
    client = client or _authed_client(token, default_client())
    detail_for = DEFAULT_DETAIL_FOR if detail_for is None else detail_for
    limit = min(n, MAX_PROFILES)

    rows = None
    last_error = None
    for template in RANKING_URLS:
        url = template.format(limit=limit)
        try:
            payload = client.get_json(url)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        rows = _entries(payload)
        if rows is not None:
            break
        last_error = RuntimeError(f"unrecognised leaderboard JSON from {url}")
        rows = None

    if not rows:
        print(
            f"  ! metaculus: no usable leaderboard "
            f"({last_error or 'empty'}). Returning no profiles."
        )
        return []

    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        user_id, username, score, rank = _row_user(row)
        if user_id is None and username is None:
            continue
        parsed.append(
            {
                "user_id": user_id or username,
                "username": username or user_id,
                "score": score,
                "rank": rank,
            }
        )
        if len(parsed) >= limit:
            break

    if not parsed:
        print("  ! metaculus: leaderboard rows had no user ids. Returning no profiles.")
        return []

    fetched_at = datetime.now(timezone.utc).isoformat()
    profiles: list[RawProfile] = []
    for i, row in enumerate(parsed):
        detail = {}
        if i < detail_for:
            for template in USER_URLS:
                url = template.format(user_id=row["user_id"])
                try:
                    payload = client.get_json(url)
                except (HttpError, Exception):
                    continue
                if isinstance(payload, dict) and (
                    payload.get("username") or payload.get("id") or payload.get("bio") is not None
                ):
                    detail = payload
                    break
        username = detail.get("username") or row["username"]
        user_id = str(detail.get("id") or row["user_id"])
        bio = detail.get("bio") or detail.get("about") or ""
        website = detail.get("website") or detail.get("url")
        twitter = detail.get("twitter") or detail.get("twitter_username")
        extra_urls = []
        if website:
            extra_urls.append(website if str(website).startswith("http") else f"https://{website}")
        if twitter:
            handle = str(twitter).lstrip("@")
            extra_urls.append(
                handle if handle.startswith("http") else f"https://twitter.com/{handle}"
            )
        profiles.append(
            RawProfile(
                platform=name,
                handle=str(username),
                display_name=detail.get("name") or username,
                url=PROFILE_URL.format(user_id=user_id),
                rating=row["score"],
                rank_pct=None,
                profile_links=_urls_from_text(bio, *extra_urls),
                country=detail.get("location") or detail.get("country"),
                raw={
                    "metric_name": "metaculus_peer_score",
                    "user_id": user_id,
                    "rank": row["rank"],
                    "bio": bio or None,
                },
                fetched_at=fetched_at,
            )
        )
    return profiles

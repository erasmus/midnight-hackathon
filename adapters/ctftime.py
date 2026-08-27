"""CTFtime adapter (issue #18).

Top 50 teams from `api/v1/top/{year}/`, then team JSON + the public team page.
Individual `RawProfile`s are emitted only when the team HTML explicitly lists
`/user/<id>` members (weak attribution — a team page is not a self-link).
Team websites / GitHub orgs are copied onto those members.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from core.http import default_client
from core.schema import RawProfile

name = "ctftime"

API = "https://ctftime.org/api/v1"
TEAM_URL = "https://ctftime.org/team/{team_id}"
USER_URL = "https://ctftime.org/user/{user_id}"
MAX_TEAMS = 50
MAX_PROFILES = 500
MEMBERS_PER_TEAM = 15

MEMBER_HREF = re.compile(r'href="/user/(\d+)/?"[^>]*>([^<]+)', re.I)
ABS_URL = re.compile(r"https?://[^\s\"'<>]+", re.I)


def _teams_from_top(payload, year: int) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    rows = payload.get(str(year)) or payload.get(year)
    if rows is None and payload:
        # Some years wrap as {"2025": [...]} even when we asked for 2026.
        first = next(iter(payload.values()))
        if isinstance(first, list):
            rows = first
    return rows if isinstance(rows, list) else []


def _member_names(html: str) -> list[tuple[str, str]]:
    """(user_id, display_name) in page order, de-duplicated."""
    seen: dict[str, str] = {}
    order: list[str] = []
    for user_id, label in MEMBER_HREF.findall(html or ""):
        name = label.strip()
        if not name or user_id in seen:
            continue
        seen[user_id] = name
        order.append(user_id)
        if len(order) >= MEMBERS_PER_TEAM:
            break
    return [(uid, seen[uid]) for uid in order]


def _org_links(html: str) -> list[str]:
    found: list[str] = []
    for url in ABS_URL.findall(html or ""):
        url = url.rstrip(").,")
        host = url.split("/")[2].lower() if "://" in url else ""
        if host.endswith("ctftime.org") or host.endswith("ctftime.org."):
            continue
        if any(part in host for part in ("github.com", "gitlab.com")) or host.count(".") >= 1:
            if "github.com" in host or "gitlab.com" in host or "http" in url:
                # Keep github/gitlab always; other http links only if they look like a homepage
                # (avoid every CDN asset). Homepages are usually in an <a>, already captured.
                if "github.com" in host or "gitlab.com" in host:
                    if url not in found:
                        found.append(url)
    # Dedicated "Site" / website anchors.
    for match in re.finditer(r'(?:Site|Website|URL)\s*</[^>]+>\s*<a href="(https?://[^"]+)"', html or "", re.I):
        url = match.group(1)
        if url not in found:
            found.append(url)
    return found


def fetch_top(
    n: int = MAX_PROFILES,
    client=None,
    year: int | None = None,
    teams: int = MAX_TEAMS,
) -> list[RawProfile]:
    client = client or default_client()
    year = datetime.now(timezone.utc).year if year is None else year
    fetched_at = datetime.now(timezone.utc).isoformat()
    top = []
    last_error = None
    for candidate in (year, year - 1):
        try:
            payload = client.get_json(f"{API}/top/{candidate}/")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        top = _teams_from_top(payload, candidate)
        if top:
            year = candidate
            break
    if not top:
        print(f"  ! ctftime: no top-team list ({last_error}). Returning no profiles.")
        return []

    top = top[:teams]
    profiles: list[RawProfile] = []
    for rank, entry in enumerate(top, start=1):
        team_id = entry.get("team_id") or entry.get("id")
        team_name = entry.get("team_name") or entry.get("name") or str(team_id)
        points = entry.get("points")
        if team_id is None:
            continue
        detail: dict = {}
        try:
            payload = client.get_json(f"{API}/teams/{team_id}/")
            if isinstance(payload, dict):
                detail = payload
        except Exception as exc:  # noqa: BLE001
            print(f"  ! ctftime team {team_id} json unavailable: {exc}")
        html = ""
        try:
            html = client.get_html(TEAM_URL.format(team_id=team_id))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! ctftime team {team_id} page unavailable: {exc}")

        country = detail.get("country")
        org_links = _org_links(html)
        members = _member_names(html)
        # API-listed members, if a future payload grows them.
        for member in detail.get("members") or []:
            if not isinstance(member, dict):
                continue
            mid = str(member.get("id") or member.get("user_id") or "")
            mname = member.get("name") or member.get("username")
            if mid and mname and mid not in {m[0] for m in members}:
                members.append((mid, mname))

        if not members:
            # No named humans — keep the team as a bonus row so org links survive.
            profiles.append(
                RawProfile(
                    platform=name,
                    handle=f"team-{team_id}",
                    display_name=team_name,
                    url=TEAM_URL.format(team_id=team_id),
                    rating=float(points) if points is not None else None,
                    profile_links=org_links,
                    country=country,
                    raw={
                        "metric_name": "ctftime_team_points",
                        "team_id": team_id,
                        "team_rank": rank,
                        "weak_attribution": True,
                        "kind": "team",
                    },
                    fetched_at=fetched_at,
                )
            )
            if len(profiles) >= min(n, MAX_PROFILES):
                return profiles
            continue

        for user_id, display in members:
            profiles.append(
                RawProfile(
                    platform=name,
                    handle=display,
                    display_name=display,
                    url=USER_URL.format(user_id=user_id),
                    rating=float(points) if points is not None else None,
                    profile_links=list(org_links),
                    country=country,
                    raw={
                        "metric_name": "ctftime_team_points",
                        "team_id": team_id,
                        "team_name": team_name,
                        "team_rank": rank,
                        "user_id": user_id,
                        "weak_attribution": True,
                        "kind": "member",
                    },
                    fetched_at=fetched_at,
                )
            )
            if len(profiles) >= min(n, MAX_PROFILES):
                return profiles
    return profiles

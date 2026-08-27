"""GitHub handle-reuse matching (issue #20).

Mechanism 2 of the consent gate, and the one that can do real damage if it is
sloppy: `github.com/<handle>` existing is *not* evidence that it is the same
person. Handle collisions are common and confidently attributing someone's
GitHub to a stranger is exactly the failure this project must not ship.

So a collision is only accepted with >=1 corroborating signal:

  * the GitHub profile's real name matches the platform display name
  * the GitHub bio mentions the source platform
  * the GitHub profile links back to the source platform

Anything else is recorded as `weak_match` and never surfaced -- it is kept
only so we can say honestly how many candidates we declined to link.

Rate limits: unauthenticated GitHub allows 60 requests/hour. Every call goes
through the shared cached, rate-limited client, and `GITHUB_TOKEN` is used
when present (5000/hour).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from core.http import default_client
from core.schema import RawProfile

GITHUB_API = "https://api.github.com"


@dataclass
class Match:
    """The verdict on one handle collision, accepted or not."""

    platform: str
    platform_handle: str
    github_login: str
    accepted: bool
    kind: str  # "handle_reuse" | "weak_match"
    evidence: str
    signals: list[str] = field(default_factory=list)
    link: str | None = None
    profile: dict = field(default_factory=dict)


def _normalise_name(name: str | None) -> str:
    return " ".join((name or "").lower().split())


def _name_corroborates(display_name: str | None, gh_name: str | None, handle: str) -> bool:
    """A shared *real* name. A single token, or the handle itself, is not one."""
    a, b = _normalise_name(display_name), _normalise_name(gh_name)
    if not a or a != b:
        return False
    if a == handle.lower():
        return False  # the collision restating itself, not evidence about it
    return len(a.split()) >= 2


def _bio_corroborates(bio: str | None, platform: str) -> bool:
    return bool(bio) and platform.lower() in bio.lower()


def _links_back(user: dict, platform: str, handle: str) -> bool:
    """Does the GitHub profile point back at the source platform?"""
    haystack = " ".join(
        str(user.get(key) or "") for key in ("blog", "company", "bio", "twitter_username")
    ).lower()
    if not haystack:
        return False
    domain = f"{platform.lower()}.com"
    return domain in haystack and (
        handle.lower() in haystack or re.search(rf"{re.escape(domain)}\S*", haystack) is not None
    )


def _headers_note() -> str:
    return "authenticated" if os.environ.get("GITHUB_TOKEN") else "unauthenticated (60/hr)"


def check_handle_reuse(profile: RawProfile, client=None) -> Match | None:
    """Look up `github.com/<handle>` and decide whether it is the same person.

    Returns `None` when there is no such GitHub account (or the lookup fails).
    Returns a `Match` with `accepted=False` for an uncorroborated collision --
    callers must never surface those.
    """
    handle = (profile.handle or "").strip()
    if not handle:
        return None

    client = client or default_client()
    try:
        user = client.get_json(f"{GITHUB_API}/users/{handle}")
    except Exception:  # noqa: BLE001 - a 404 is the common, expected case
        return None
    if not user or not user.get("login"):
        return None

    login = user["login"]
    signals: list[str] = []

    if _name_corroborates(profile.display_name, user.get("name"), handle):
        signals.append(
            f"GitHub real name {user.get('name')!r} matches the "
            f"{profile.platform} display name {profile.display_name!r}"
        )
    if _bio_corroborates(user.get("bio"), profile.platform):
        signals.append(f"GitHub bio mentions {profile.platform}: {user.get('bio')!r}")
    if _links_back(user, profile.platform, handle):
        signals.append(
            f"GitHub profile links back to {profile.platform} "
            f"({user.get('blog') or user.get('company')!r})"
        )

    url = user.get("html_url") or f"https://github.com/{login}"

    if signals:
        return Match(
            platform=profile.platform,
            platform_handle=handle,
            github_login=login,
            accepted=True,
            kind="handle_reuse",
            signals=signals,
            link=url,
            profile=user,
            evidence=(
                f"{profile.platform} handle {handle!r} also exists on GitHub "
                f"({url}), corroborated by: " + "; ".join(signals)
            ),
        )

    return Match(
        platform=profile.platform,
        platform_handle=handle,
        github_login=login,
        accepted=False,
        kind="weak_match",
        signals=[],
        link=None,
        profile=user,
        evidence=(
            f"github.com/{login} shares the {profile.platform} handle {handle!r} "
            "but there is no corroborating signal (no matching real name, no "
            "platform mention in the bio, no link back), so the accounts are "
            "not treated as the same person"
        ),
    )

"""Self-link extraction and classification (issue #19).

Mechanism 1 of the consent gate. Every off-platform link we ever act on comes
from here: a URL the person *published themselves* on a profile they control.
Nothing is inferred, nothing is unmasked.

Each extracted link carries a human-readable evidence string naming the source
platform and, where the adapter recorded it, the field it came from. If a link
cannot be explained in a sentence, it does not get used.

Unrecognised domains are kept as `personal_site` candidates rather than dropped
silently -- a personal domain is often the strongest signal we have.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from core.schema import RawProfile

GITHUB = "github"
LINKEDIN = "linkedin"
TWITTER = "twitter"
PERSONAL_SITE = "personal_site"

# github.com/<these> are product pages, not user profiles.
GITHUB_RESERVED = frozenset(
    {
        "orgs", "organizations", "settings", "features", "pricing", "about",
        "explore", "topics", "collections", "events", "sponsors", "marketplace",
        "notifications", "issues", "pulls", "search", "login", "join", "new",
        "apps", "enterprise", "security", "readme", "trending", "codespaces",
    }
)

TWITTER_RESERVED = frozenset({"home", "search", "explore", "i", "intent", "share"})


@dataclass(frozen=True)
class Link:
    """One self-published link, with the provenance that justifies using it."""

    url: str
    kind: str
    handle: str | None
    source_platform: str
    source_handle: str
    source_field: str
    evidence: str


def _normalise(url: str) -> str | None:
    url = (url or "").strip()
    if not url or " " in url:
        return None
    if url.startswith(("mailto:", "tel:")):
        return None
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    return url


def _parts(url: str) -> tuple[str, list[str]]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    segments = [s for s in parsed.path.split("/") if s]
    return host, segments


def classify(url: str) -> tuple[str, str | None]:
    """Return `(kind, handle)`. Unknown hosts are `personal_site` candidates."""
    normalised = _normalise(url)
    if normalised is None:
        return PERSONAL_SITE, None
    host, segments = _parts(normalised)
    first = segments[0].lower() if segments else None

    if host == "github.com":
        if first and first not in GITHUB_RESERVED:
            return GITHUB, segments[0]
        return GITHUB, None

    if host == "linkedin.com":
        # Only /in/ is a person; /company/ and /school/ are organisations.
        if len(segments) >= 2 and first == "in":
            return LINKEDIN, segments[1]
        return PERSONAL_SITE, None

    if host in ("twitter.com", "x.com"):
        if first and first not in TWITTER_RESERVED:
            return TWITTER, segments[0]
        return PERSONAL_SITE, None

    return PERSONAL_SITE, None


def _dedupe_key(url: str) -> str:
    normalised = _normalise(url) or url
    return normalised.rstrip("/").lower()


def extract_links(profile: RawProfile) -> list[Link]:
    """Every `profile_links` entry, classified and evidenced.

    Adapters may record which field a URL came from in
    `raw["link_sources"]` (`{url: field}`); when absent the evidence falls
    back to naming the profile generally.
    """
    sources = (profile.raw or {}).get("link_sources") or {}
    seen: set[str] = set()
    links: list[Link] = []

    for url in profile.profile_links or []:
        normalised = _normalise(url)
        if normalised is None:
            continue
        key = _dedupe_key(normalised)
        if key in seen:
            continue
        seen.add(key)

        kind, handle = classify(normalised)
        field = sources.get(url) or sources.get(normalised) or "profile links"
        links.append(
            Link(
                url=normalised,
                kind=kind,
                handle=handle,
                source_platform=profile.platform,
                source_handle=profile.handle,
                source_field=field,
                evidence=(
                    f"{profile.platform} profile {profile.handle} lists "
                    f"{normalised} in its {field}"
                ),
            )
        )
    return links

"""Identity resolution and the merge rule (issues #19-#22, Epic 3).

This is the consent gate, and it is deliberately dumb. Exactly three sanctioned
mechanisms may ever merge two profiles into one Person:

  1. **Self-link** -- profile A publishes a URL pointing at profile B.
  2. **Corroborated handle reuse** -- both profiles resolve to the same GitHub
     account *with* a corroborating signal (see core.github_match).
  3. **FIDE join** -- issue #21, not yet built; the hook is `FIDE_JOIN` below.

Nothing else merges. Not a shared display name, not a shared handle, not a
country plus a rating band. Precision over recall: twenty correct people beat
two hundred with three errors, because one wrong link shown to a judge
discredits the entire shortlist.

All merging goes through `_union` inside `resolve()` -- one function, one entry
point -- so "is there another way two people can become one?" is answerable by
reading this file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from core.github_match import check_handle_reuse
from core.links import GITHUB, extract_links
from core.schema import Person, RawProfile

# Public profile URL shapes, used to tell "this link points at another profile
# we already fetched" from "this link points off-platform".
PLATFORM_PROFILE_PATTERNS: dict[str, re.Pattern] = {
    "codeforces": re.compile(r"^codeforces\.com/profile/([^/?#]+)", re.I),
    "lichess": re.compile(r"^lichess\.org/@/([^/?#]+)", re.I),
    "kaggle": re.compile(r"^kaggle\.com/([^/?#]+)", re.I),
    "metaculus": re.compile(r"^metaculus\.com/accounts/profile/([^/?#]+)", re.I),
}

# Mechanism 3 lands with #21 (FIDE adapter #15 must exist first).
FIDE_JOIN = None

# GitHub is 60 requests/hour unauthenticated, so only the sharp end is checked.
DEFAULT_GITHUB_FOR = 50


def identify_platform_profile(url: str) -> tuple[str, str] | None:
    """`(platform, handle)` if this URL is a profile page we know how to read."""
    stripped = re.sub(r"^https?://", "", (url or "").strip(), flags=re.I)
    stripped = re.sub(r"^www\.", "", stripped, flags=re.I)
    for platform, pattern in PLATFORM_PROFILE_PATTERNS.items():
        match = pattern.match(stripped)
        if match:
            return platform, match.group(1)
    return None


def _key(platform: str, handle: str) -> str:
    return f"{platform}:{handle}".lower()


@dataclass
class _Node:
    profile: RawProfile
    links: dict[str, str] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    weak: list[str] = field(default_factory=list)


def _real_name_score(name: str | None, handle: str) -> int:
    """Prefer a published real name over a handle when naming a Person."""
    if not name:
        return 0
    if name.strip().lower() == handle.strip().lower():
        return 0
    return 2 if len(name.split()) >= 2 else 1


def passthrough(profiles: list[RawProfile]) -> list[Person]:
    """One Person per profile, no merging -- what `--skip-resolve` means.

    Downstream stages still need people to work on, so skipping resolution
    degrades to the identity mapping rather than to nothing.
    """
    return [
        Person(
            id=_key(p.platform, p.handle),
            display_name=p.display_name or p.handle,
            birth_year=p.birth_year,
            country=p.country,
            profiles=[p],
        )
        for p in profiles
    ]


def resolve(
    profiles: list[RawProfile],
    github_client=None,
    github_for: int | None = None,
) -> list[Person]:
    """Merge profiles into people via the sanctioned mechanisms only."""
    github_for = DEFAULT_GITHUB_FOR if github_for is None else github_for

    nodes: dict[str, _Node] = {}
    for profile in profiles:
        nodes.setdefault(_key(profile.platform, profile.handle), _Node(profile=profile))

    parent: dict[str, str] = {k: k for k in nodes}

    def _find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def _union(a: str, b: str, why: str) -> None:
        """THE ONLY MERGE PATH. Every caller must supply a reason."""
        ra, rb = _find(a), _find(b)
        if ra == rb:
            return
        # Merge into the lexicographically smaller root, so runs are stable.
        lo, hi = sorted((ra, rb))
        parent[hi] = lo
        nodes[lo].evidence.append(why)

    # -- mechanism 1: self-links ------------------------------------------
    for key in sorted(nodes):
        node = nodes[key]
        for link in extract_links(node.profile):
            target = identify_platform_profile(link.url)
            if target:
                target_key = _key(*target)
                if target_key in nodes and target_key != key:
                    _union(
                        key,
                        target_key,
                        f"merged: {link.evidence}, which is the "
                        f"{target[0]} profile {target[1]}",
                    )
                continue
            # Off-platform link: recorded, with its provenance, never merged on.
            node.links.setdefault(link.kind, link.url)
            node.evidence.append(link.evidence)

    # -- mechanism 2: corroborated GitHub handle reuse ---------------------
    if github_for:
        by_github: dict[str, str] = {}
        for key in list(nodes)[:github_for]:
            node = nodes[key]
            match = check_handle_reuse(node.profile, client=github_client)
            if match is None:
                continue
            if not match.accepted:
                node.weak.append(match.evidence)
                continue
            node.links.setdefault(GITHUB, match.link)
            node.evidence.append(match.evidence)
            login = match.github_login.lower()
            if login in by_github:
                _union(
                    by_github[login],
                    key,
                    f"merged: both profiles resolve to github.com/{match.github_login} "
                    f"with corroboration ({match.evidence})",
                )
            else:
                by_github[login] = key

    # -- mechanism 3: FIDE join (#21) -------------------------------------
    if FIDE_JOIN is not None:  # pragma: no cover - lands with #21
        FIDE_JOIN(nodes, _union)

    # -- build people ------------------------------------------------------
    components: dict[str, list[str]] = {}
    for key in sorted(nodes):
        components.setdefault(_find(key), []).append(key)

    persons: list[Person] = []
    for root, members in sorted(components.items()):
        members.sort()
        member_nodes = [nodes[m] for m in members]
        best = max(
            member_nodes,
            key=lambda n: (
                _real_name_score(n.profile.display_name, n.profile.handle),
                n.profile.platform,
            ),
        )
        links: dict[str, str] = {}
        evidence: list[str] = []
        weak: list[str] = []
        for node in member_nodes:
            for kind, url in node.links.items():
                links.setdefault(kind, url)
            for item in node.evidence:
                if item not in evidence:
                    evidence.append(item)
            weak.extend(node.weak)

        persons.append(
            Person(
                id=members[0],
                display_name=best.profile.display_name or best.profile.handle,
                birth_year=next(
                    (n.profile.birth_year for n in member_nodes if n.profile.birth_year), None
                ),
                country=next(
                    (n.profile.country for n in member_nodes if n.profile.country), None
                ),
                profiles=[n.profile for n in member_nodes],
                links=links,
                evidence=evidence,
                weak_matches=weak,
            )
        )
    return persons

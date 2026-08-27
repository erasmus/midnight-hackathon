"""OpenAlex adapter (issue #17).

Source: young, highly cited authors in CS / ML / bio (first counted year
within the last 6 years, citations above a floor). Enricher: `lookup_papers`
by name (+ optional institution) for Epic 4.

No API key. Polite User-Agent is already set on the shared client.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from core.http import default_client
from core.schema import RawProfile

name = "openalex"

API = "https://api.openalex.org"
MAX_PROFILES = 200
# Computer science | machine learning | biology (OpenAlex concept IDs).
CONCEPT_IDS = "C41008148|C119599485|C86803240"
CITATION_FLOOR = 80
MAX_WORKS = 80
CAREER_YEARS = 6
PAGE_SIZE = 50
MAX_PAGES = 8


def _year_now() -> int:
    return datetime.now(timezone.utc).year


def _first_year(author: dict) -> int | None:
    years = [
        c.get("year")
        for c in (author.get("counts_by_year") or [])
        if c.get("works_count")
    ]
    years = [y for y in years if isinstance(y, int)]
    return min(years) if years else None


def _institution(author: dict) -> str | None:
    insts = author.get("last_known_institutions") or author.get("affiliations") or []
    if not insts:
        return None
    first = insts[0]
    if isinstance(first, dict):
        return first.get("display_name") or (first.get("institution") or {}).get("display_name")
    return None


def _links(author: dict, works: list[dict] | None = None) -> list[str]:
    found: list[str] = []

    def add(url: str | None) -> None:
        if url and url not in found:
            found.append(url)

    ids = author.get("ids") or {}
    add(author.get("orcid") or ids.get("orcid"))
    add(ids.get("wikipedia"))
    add(author.get("id"))
    for work in works or []:
        loc = work.get("primary_location") or work.get("best_oa_location") or {}
        add((loc or {}).get("landing_page_url"))
        source = (loc or {}).get("source") or {}
        homepage = source.get("homepage_url") if isinstance(source, dict) else None
        if homepage and "github.com" in homepage:
            add(homepage)
        for location in work.get("locations") or []:
            url = (location or {}).get("landing_page_url") or ""
            if "github.com" in url:
                add(url)
    return found


def _openalex_id(url_or_id: str) -> str:
    text = url_or_id.rstrip("/")
    return text.rsplit("/", 1)[-1]


def _authors_url(page: int) -> str:
    params = {
        "filter": (
            f"concepts.id:{CONCEPT_IDS},"
            f"cited_by_count:>{CITATION_FLOOR},"
            f"works_count:<{MAX_WORKS}"
        ),
        "sort": "cited_by_count:desc",
        "per-page": PAGE_SIZE,
        "page": page,
    }
    return f"{API}/authors?{urlencode(params)}"


def fetch_top(n: int = MAX_PROFILES, client=None) -> list[RawProfile]:
    client = client or default_client()
    limit = min(n, MAX_PROFILES)
    cutoff = _year_now() - CAREER_YEARS
    fetched_at = datetime.now(timezone.utc).isoformat()
    profiles: list[RawProfile] = []

    for page in range(1, MAX_PAGES + 1):
        try:
            payload = client.get_json(_authors_url(page))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! openalex authors page {page} failed: {exc}")
            break
        results = payload.get("results") if isinstance(payload, dict) else None
        if not results:
            break
        for author in results:
            first = _first_year(author)
            if first is None or first < cutoff:
                continue
            cited = author.get("cited_by_count") or 0
            career = max(1, _year_now() - first)
            velocity = cited / career
            openalex_id = _openalex_id(author.get("id") or "")
            inst = _institution(author)
            insts = author.get("last_known_institutions") or []
            country = insts[0].get("country_code") if insts and isinstance(insts[0], dict) else None
            profiles.append(
                RawProfile(
                    platform=name,
                    handle=openalex_id,
                    display_name=author.get("display_name"),
                    url=author.get("id"),
                    rating=float(velocity),
                    rank_pct=None,
                    profile_links=_links(author),
                    country=country,
                    raw={
                        "metric_name": "citation_velocity",
                        "cited_by_count": cited,
                        "works_count": author.get("works_count"),
                        "first_year": first,
                        "institution": inst,
                        "orcid": author.get("orcid") or (author.get("ids") or {}).get("orcid"),
                    },
                    fetched_at=fetched_at,
                )
            )
            if len(profiles) >= limit:
                return profiles
        if len(results) < PAGE_SIZE:
            break
    return profiles


def lookup_papers(
    name: str,
    institution: str | None = None,
    client=None,
    per_page: int = 5,
) -> list[dict[str, Any]]:
    """Enricher: papers for a real name, or [] if OpenAlex has nothing."""
    client = client or default_client()
    query = name if not institution else f"{name} {institution}"
    try:
        payload = client.get_json(
            f"{API}/works?{urlencode({'search': query, 'per-page': per_page, 'sort': 'cited_by_count:desc'})}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ! openalex works search failed for {name!r}: {exc}")
        return []
    results = payload.get("results") if isinstance(payload, dict) else None
    if not results:
        return []
    papers = []
    for work in results:
        loc = work.get("primary_location") or {}
        papers.append(
            {
                "id": work.get("id"),
                "title": work.get("display_name") or work.get("title"),
                "year": work.get("publication_year"),
                "cited_by_count": work.get("cited_by_count"),
                "doi": (work.get("ids") or {}).get("doi"),
                "landing_page_url": (loc or {}).get("landing_page_url"),
                "authorships": [
                    (a.get("author") or {}).get("display_name")
                    for a in (work.get("authorships") or [])
                    if (a.get("author") or {}).get("display_name")
                ],
            }
        )
    return papers


def github_urls_from_papers(papers: list[dict]) -> list[str]:
    found: list[str] = []
    for paper in papers:
        url = paper.get("landing_page_url") or ""
        if "github.com" in url and url not in found:
            found.append(url)
    return found

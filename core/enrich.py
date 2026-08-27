"""Stage: enrichment (stub -- Epic 4, issues #23-#25).

Eventually: GitHub enrichment, founder-already detection, and storing (never
scraping) LinkedIn/website links. Passes people through untouched for now.
"""

from __future__ import annotations

from core.schema import Person


def enrich(persons: list[Person]) -> list[Person]:
    return persons


def lookup_papers(name: str, institution: str | None = None, client=None):
    """Epic 4 hook: OpenAlex papers for a resolved name (issue #17 enricher)."""
    from adapters import openalex as openalex_adapter

    return openalex_adapter.lookup_papers(name, institution=institution, client=client)

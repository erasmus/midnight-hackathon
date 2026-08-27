"""Stage: enrichment (stub -- Epic 4, issues #23-#25).

Eventually: GitHub enrichment, founder-already detection, and storing (never
scraping) LinkedIn/website links. Passes people through untouched for now.
"""

from __future__ import annotations

from core.schema import Person


def enrich(persons: list[Person]) -> list[Person]:
    return persons

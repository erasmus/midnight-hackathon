"""Stage: identity resolution (stub -- Epic 3, issues #19-#22).

Eventually: self-link extraction, GitHub handle-reuse matching, FIDE join, and
the merge rule that turns several RawProfiles into one Person.

The stub is the degenerate merge: one Person per profile, no cross-platform
links, so downstream stages can be built and tested before Epic 3 lands.
"""

from __future__ import annotations

from core.schema import Person, RawProfile


def resolve(profiles: list[RawProfile]) -> list[Person]:
    return [
        Person(
            id=f"{p.platform}:{p.handle}",
            display_name=p.display_name or p.handle,
            birth_year=p.birth_year,
            country=p.country,
            profiles=[p],
        )
        for p in profiles
    ]

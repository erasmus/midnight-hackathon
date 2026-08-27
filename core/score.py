"""Stage: scoring and ranking (stub -- Epic 5, issues #26-#30).

Eventually: hard filters, then outlierness / trajectory / addressability on a
0-100 scale, combined into a composite with flags. The stub emits a Scores row
per person with everything unset, so persistence and outputs are exercisable.
"""

from __future__ import annotations

from core.schema import Person, Scores


def score(persons: list[Person]) -> list[Scores]:
    return [Scores(person_id=p.id) for p in persons]


def rank(scores: list[Scores]) -> list[Scores]:
    return sorted(scores, key=lambda s: (s.composite is None, -(s.composite or 0.0)))

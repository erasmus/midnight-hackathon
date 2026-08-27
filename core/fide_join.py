"""FIDE join for titled chess players (issue #21).

Mechanism 3 of the consent gate, and the one that unlocks the age gate: a
successful join copies a *verified* `birth_year` from the official FIDE rating
list onto the person.

The rule is deliberately strict:

  * **exact** title match (an IM is not the GM of the same name), and
  * fuzzy name similarity **>= 0.9**.

Anything between 0.8 and the threshold is logged as a near miss and left
unmerged -- visible, so we can say what we declined, but never asserted.
Ambiguous FIDE entries (two titled players sharing a name) are refused
outright: there is no confident answer, so we don't invent one.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from adapters.fide import PROFILE_URL, normalise_name

MIN_SIMILARITY = 0.9
# Close-but-refused, worth showing a human. Below this it isn't even a near miss.
NEAR_MISS_SIMILARITY = 0.8


@dataclass
class FideMatch:
    record: dict
    similarity: float
    evidence: str


def build_buckets(index: dict[tuple[str, str], dict]) -> dict[str, list[tuple[str, dict]]]:
    """Group the join index by title, so fuzzy search stays within a title."""
    buckets: dict[str, list[tuple[str, dict]]] = {}
    for (title, normalised), record in index.items():
        buckets.setdefault(title, []).append((normalised, record))
    return buckets


def _best(title: str, normalised: str, buckets) -> tuple[dict | None, float]:
    best_record, best_score = None, 0.0
    for candidate_name, record in buckets.get(title, ()):
        score = SequenceMatcher(None, normalised, candidate_name).ratio()
        if score > best_score:
            best_record, best_score = record, score
    return best_record, best_score


def find_match(title: str | None, display_name: str | None, buckets) -> FideMatch | None:
    """The FIDE record for this titled player, or None if we can't be sure."""
    if not title or not display_name:
        return None
    normalised = normalise_name(display_name)
    if not normalised:
        return None

    record, score = _best(title, normalised, buckets)
    if record is None or score < MIN_SIMILARITY:
        return None
    if record.get("ambiguous"):
        # Two titled players share this name: no confident answer exists.
        return None

    return FideMatch(
        record=record,
        similarity=score,
        evidence=(
            f"FIDE join: title {title} matches exactly and name "
            f"{display_name!r} matches FIDE record {record['name']!r} "
            f"at similarity {score:.2f} (>= {MIN_SIMILARITY}); "
            f"birth year {record['birth_year']} taken from the official "
            f"FIDE rating list, FIDE ID {record['fideid']}"
        ),
    )


def near_miss(title: str | None, display_name: str | None, buckets) -> str | None:
    """A close-but-refused candidate, for honest reporting."""
    if not title or not display_name:
        return None
    normalised = normalise_name(display_name)
    record, score = _best(title, normalised, buckets)
    if record is None or not (NEAR_MISS_SIMILARITY <= score < MIN_SIMILARITY):
        return None
    return (
        f"FIDE near miss: {display_name!r} ({title}) resembles FIDE record "
        f"{record['name']!r} at similarity {score:.2f}, below the "
        f"{MIN_SIMILARITY} threshold, so no join was made"
    )


def profile_title(profile) -> str | None:
    """The FIDE title a profile declares, if any."""
    return (profile.raw or {}).get("title") or None


def fide_profile_url(record: dict) -> str:
    return PROFILE_URL.format(fideid=record["fideid"])

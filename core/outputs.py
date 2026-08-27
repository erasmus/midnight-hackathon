"""Outputs: the shortlist CSV (issue #31).

The shortlist is the artefact a human actually reads, so it is written to be
read: evidence is semicolon-joined prose, not JSON; links are plain URLs; and
**only hard-filter survivors appear**. Everyone else stays in the database with
their exclusion reasons, which is where an auditor should look -- not here.
"""

from __future__ import annotations

import csv
from pathlib import Path

from core.schema import Person, Scores
from core.score import DOMAINS

SHORTLIST_FILENAME = "shortlist.csv"
SHORTLIST_SIZE = 20

SHORTLIST_COLUMNS = (
    "rank",
    "person_id",
    "name",
    "country",
    "birth_year",
    "domains",
    "key_achievement",
    "outlierness",
    "trajectory",
    "addressability",
    "composite",
    "flags",
    "links",
    "evidence",
)


def _domains(person: Person) -> str:
    found = sorted({DOMAINS[p.platform] for p in person.profiles if p.platform in DOMAINS})
    return ", ".join(found)


def key_achievement(person: Person) -> str:
    """One human-readable line naming the person's strongest single result."""
    if not person.profiles:
        return ""

    def strength(profile):
        return (profile.rank_pct or 0, profile.rating or 0)

    best = max(person.profiles, key=strength)
    parts = [best.platform]
    title = (best.raw or {}).get("title")
    if title:
        parts.append(str(title))
    if best.rating is not None:
        parts.append(f"rating {best.rating:g}")
    if best.rank_pct is not None:
        parts.append(f"top {100 - best.rank_pct:.2f}%")
    return " · ".join(parts)


def _links(person: Person) -> str:
    return "; ".join(f"{kind}: {url}" for kind, url in sorted(person.links.items()))


def shortlist_rows(
    persons: list[Person], scores: list[Scores], limit: int = SHORTLIST_SIZE
) -> list[dict]:
    """Survivors only, best first, capped at `limit`."""
    by_id = {p.id: p for p in persons}
    survivors = [
        s for s in scores if not s.excluded and s.person_id in by_id
    ]
    survivors.sort(key=lambda s: (-(s.composite or 0.0), s.person_id))

    rows = []
    for position, score in enumerate(survivors[:limit], start=1):
        person = by_id[score.person_id]
        rows.append(
            {
                "rank": position,
                "person_id": person.id,
                "name": person.display_name or "",
                "country": person.country or "",
                "birth_year": person.birth_year or "",
                "domains": _domains(person),
                "key_achievement": key_achievement(person),
                "outlierness": score.outlierness,
                "trajectory": score.trajectory,
                "addressability": score.addressability,
                "composite": score.composite,
                "flags": ", ".join(score.flags),
                "links": _links(person),
                "evidence": "; ".join(person.evidence),
            }
        )
    return rows


def write_shortlist(
    persons: list[Person], scores: list[Scores], out_dir: str | Path
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SHORTLIST_FILENAME

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SHORTLIST_COLUMNS))
        writer.writeheader()
        writer.writerows(shortlist_rows(persons, scores))
    return path


def write_outputs(
    persons: list[Person], scores: list[Scores], out_dir: str | Path
) -> list[Path]:
    """The shortlist, plus one dossier per person on it.

    Dossiers are written only for hard-filter survivors: an excluded person is
    auditable in the database, but producing a polished one-pager about someone
    we refused would invite exactly the misuse the filters exist to prevent.
    """
    from dossier import write_dossier  # local import: dossier imports outputs' deps

    paths = [write_shortlist(persons, scores, out_dir)]

    by_id = {p.id: p for p in persons}
    scores_by_id = {s.person_id: s for s in scores}
    for row in shortlist_rows(persons, scores):
        person = by_id[row["person_id"]]
        paths.append(write_dossier(person, scores_by_id[person.id], out_dir))
    return paths

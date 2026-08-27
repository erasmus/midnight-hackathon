"""Stage: outputs (Epic 6, issues #31–#33).

Writes `shortlist.csv` (top 20 by composite, hard-filter survivors only) and a
dossier HTML one-pager for the #1 row. `python dossier.py <id>` re-renders any
person already in the DB.
"""

from __future__ import annotations

import csv
from pathlib import Path

from core.schema import Person, Scores
from dossier import domains, key_achievement, write_dossier

SHORTLIST_N = 20
# Scoring (Epic 5) is supposed to drop these before we ever see them. Belt and
# braces so a stub or a leak cannot put a founder on a spreadsheet a judge opens.
EXCLUDED_FLAGS = frozenset({"already_founder"})

CSV_COLUMNS = [
    "name",
    "domains",
    "key_achievement",
    "outlierness",
    "trajectory",
    "addressability",
    "composite",
    "links",
    "evidence",
    "person_id",
]


def survivors(persons: list[Person], scores: list[Scores]) -> list[tuple[Person, Scores]]:
    by_id = {p.id: p for p in persons}
    ranked: list[tuple[Person, Scores]] = []
    for score in scores:
        if EXCLUDED_FLAGS.intersection(score.flags):
            continue
        person = by_id.get(score.person_id)
        if person is None:
            continue
        ranked.append((person, score))
    ranked.sort(key=lambda pair: (pair[1].composite is None, -(pair[1].composite or 0.0)))
    return ranked


def _links_cell(person: Person) -> str:
    urls = list(person.links.values())
    for profile in person.profiles:
        if profile.url:
            urls.append(profile.url)
        urls.extend(profile.profile_links)
    # Preserve order, drop dupes. Semicolon-joined so a spreadsheet doesn't
    # explode JSON into columns.
    seen: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.append(url)
    return "; ".join(seen)


def write_shortlist_csv(pairs: list[tuple[Person, Scores]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for person, score in pairs[:SHORTLIST_N]:
            writer.writerow(
                {
                    "name": person.display_name or person.id,
                    "domains": "; ".join(domains(person)),
                    "key_achievement": key_achievement(person),
                    "outlierness": score.outlierness,
                    "trajectory": score.trajectory,
                    "addressability": score.addressability,
                    "composite": score.composite,
                    "links": _links_cell(person),
                    "evidence": "; ".join(person.evidence),
                    "person_id": person.id,
                }
            )
    return path


def write_outputs(persons: list[Person], scores: list[Scores], out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs = survivors(persons, scores)
    written = [write_shortlist_csv(pairs, out_dir / "shortlist.csv")]
    if pairs:
        written.append(write_dossier(pairs[0][0], pairs[0][1], out_dir))
    return written

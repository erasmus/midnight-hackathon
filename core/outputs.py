"""Stage: outputs (stub -- Epic 6, issues #31-#34).

Eventually: shortlist.csv and the dossier one-pager. For now it just creates
the output directory so the pipeline's contract with Epic 6 is already in place.
"""

from __future__ import annotations

from pathlib import Path

from core.schema import Person, Scores


def write_outputs(persons: list[Person], scores: list[Scores], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return []

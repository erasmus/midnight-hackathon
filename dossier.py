"""Dossier one-pager generator (stub -- Epic 6, issue #32).

Entry point kept here so `pipeline.py` and the demo script have a stable
import path before the generator itself is written.
"""

from __future__ import annotations

from pathlib import Path

from core.schema import Person, Scores


def render_dossier(person: Person, scores: Scores) -> str:
    raise NotImplementedError("Dossier rendering lands with issue #32.")


def write_dossier(person: Person, scores: Scores, out_dir: Path) -> Path:
    raise NotImplementedError("Dossier rendering lands with issue #32.")

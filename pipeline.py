"""Pipeline orchestrator (issue #8).

    adapters -> normalize -> resolve -> enrich -> score -> rank -> persist -> outputs

Every stage after `adapters` is a stub today (Epics 2-6 fill them in), but the
wiring, the DB and the CLI are real, so an adapter can be dropped into
`adapters/` and immediately run end-to-end.

Adapter interface: a module (or object) exposing

    fetch_top(n: int) -> list[RawProfile]

Any stage can be skipped (`--skip-enrich`) so partial runs stay possible when
something upstream is broken mid-hackathon.

Usage:
    python pipeline.py                       # full run into ./db.sqlite
    python pipeline.py --top 50 --skip-enrich
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from core import enrich as enrich_stage
from core import normalize as normalize_stage
from core import outputs as outputs_stage
from core import resolve as resolve_stage
from core import score as score_stage
from core.db import DEFAULT_DB_PATH, Database
from core.schema import Person, RawProfile, Scores

SKIPPABLE_STAGES = ("fetch", "normalize", "resolve", "enrich", "score", "outputs")
DEFAULT_TOP_N = 100
DEFAULT_OUT_DIR = Path("out")


@dataclass
class RunResult:
    raw_profiles: list[RawProfile] = field(default_factory=list)
    persons: list[Person] = field(default_factory=list)
    scores: list[Scores] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    outputs: list[Path] = field(default_factory=list)
    adapter_errors: dict[str, str] = field(default_factory=dict)


def adapter_name(adapter: Any) -> str:
    return getattr(adapter, "name", None) or getattr(adapter, "__name__", repr(adapter))


def collect(adapters: Iterable[Any], top_n: int, errors: dict[str, str]) -> list[RawProfile]:
    """Run every adapter. One broken source must not sink the whole run."""
    profiles: list[RawProfile] = []
    for adapter in adapters:
        name = adapter_name(adapter)
        try:
            fetched = adapter.fetch_top(top_n)
        except Exception as exc:  # noqa: BLE001 - a dead source is expected
            errors[name] = str(exc)
            print(f"  ! adapter {name} failed: {exc}", file=sys.stderr)
            continue
        profiles.extend(fetched)
        print(f"  + adapter {name}: {len(fetched)} profiles")
    return profiles


def run(
    adapters: Sequence[Any] = (),
    db_path: str | Path = DEFAULT_DB_PATH,
    out_dir: str | Path = DEFAULT_OUT_DIR,
    top_n: int = DEFAULT_TOP_N,
    skip: Sequence[str] = (),
    github_for: int = 0,
) -> RunResult:
    unknown = [s for s in skip if s not in SKIPPABLE_STAGES]
    if unknown:
        raise ValueError(
            f"Unknown stage(s) to skip: {unknown}. Known: {list(SKIPPABLE_STAGES)}"
        )

    result = RunResult(skipped=list(skip))

    def active(stage: str) -> bool:
        if stage in skip:
            print(f"  - skipping {stage}")
            return False
        return True

    with Database(db_path) as db:
        # --skip-fetch re-runs the rest of the pipeline over whatever is
        # already in the DB: no network, no waiting on someone else's API.
        if active("fetch"):
            print("fetching...")
            profiles = collect(adapters, top_n, result.adapter_errors)
            if active("normalize"):
                profiles = normalize_stage.normalize(profiles)
            db.upsert_raw_profiles(profiles)
        result.raw_profiles = db.all_raw_profiles()

        # Resolve is what turns profiles into people; skipping it still needs to
        # yield people, otherwise every downstream stage has nothing to chew on.
        if active("resolve"):
            persons = resolve_stage.resolve(
                result.raw_profiles, github_for=github_for
            )
        else:
            persons = resolve_stage.passthrough(result.raw_profiles)

        if active("enrich"):
            persons = enrich_stage.enrich(persons)
        db.upsert_persons(persons)
        result.persons = persons

        if active("score"):
            scores = score_stage.rank(score_stage.score(persons))
            db.upsert_scores(scores)
            result.scores = scores

        if active("outputs"):
            result.outputs = outputs_stage.write_outputs(
                result.persons, result.scores, Path(out_dir)
            )

    print(
        f"done: {len(result.raw_profiles)} profiles, {len(result.persons)} persons, "
        f"{len(result.scores)} scored -> {db_path}"
    )
    return result


def discover_adapters() -> list[Any]:
    """Import every adapter module in `adapters/` that exposes `fetch_top`."""
    import importlib
    import pkgutil

    import adapters as adapters_pkg

    found = []
    for module_info in pkgutil.iter_modules(adapters_pkg.__path__):
        module = importlib.import_module(f"adapters.{module_info.name}")
        if hasattr(module, "fetch_top"):
            found.append(module)
    return found


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite path")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="output directory")
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP_N, help="profiles to request per adapter"
    )
    # Off by default: unauthenticated GitHub allows 60 requests/hour, so this
    # is opt-in rather than something a casual run burns through by accident.
    parser.add_argument(
        "--github-for",
        type=int,
        default=0,
        metavar="N",
        help="check GitHub handle reuse for the top N people "
        "(0 = off; set GITHUB_TOKEN to raise the 60/hr limit)",
    )
    for stage in SKIPPABLE_STAGES:
        parser.add_argument(
            f"--skip-{stage}", action="store_true", help=f"skip the {stage} stage"
        )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    skip = [s for s in SKIPPABLE_STAGES if getattr(args, f"skip_{s}")]
    run(
        adapters=discover_adapters(),
        db_path=args.db,
        out_dir=args.out,
        top_n=args.top,
        skip=skip,
        github_for=args.github_for,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

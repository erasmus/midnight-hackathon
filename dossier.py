"""Dossier one-pager (issue #32).

    python dossier.py <person_id> --db db.sqlite --out out/

Writes a self-contained HTML file. No send button, no mailer, no scrape of
LinkedIn. Every URL on the page is one the candidate published; provenance
lives in the evidence appendix (Person.evidence, not the truncated links dict).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

from core.db import DEFAULT_DB_PATH, Database
from core.schema import Person, Scores
from core.sparkline import collect_history, sparkline_svg

DRAFT_LABEL = "DRAFT — edit before sending"
CSS = """
:root { --paper:#f3ead8; --ink:#1c1814; --soft:#5c5348; --brass:#9a6b1f; --line:#d9cbb0; }
body { margin:0; background:#100e0b; color:var(--ink); font-family:Georgia,serif; }
.wrap { max-width:720px; margin:32px auto; background:var(--paper); padding:40px 44px 56px; }
h1 { font-weight:400; font-size:2.2rem; letter-spacing:-0.03em; margin:0 0 4px; }
.meta { color:var(--soft); font-size:0.9rem; margin-bottom:16px; font-family:ui-sans-serif,system-ui,sans-serif; }
.why { font-size:1.15rem; line-height:1.4; margin:0 0 24px; }
.scores { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; border-top:1px solid var(--line);
  border-bottom:1px solid var(--line); padding:16px 0; margin-bottom:24px; }
.scores .lbl { font-family:ui-monospace,monospace; font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--soft); }
.scores .val { font-size:1.7rem; }
h2 { font-family:ui-monospace,monospace; font-size:11px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--brass); font-weight:500; margin:28px 0 12px; }
.row { display:grid; grid-template-columns:8rem 1fr auto; gap:8px 16px; padding:10px 0;
  border-bottom:1px solid var(--line); font-family:ui-sans-serif,system-ui,sans-serif; font-size:0.95rem; }
a { color:var(--brass); }
.draft { border:1px dashed var(--brass); padding:14px 16px; background:rgba(154,107,31,.08); }
.draft strong { font-family:ui-monospace,monospace; font-size:10px; letter-spacing:.12em; color:#8a3b28;
  display:block; margin-bottom:8px; }
.spark { width:100%; height:88px; display:block; }
.cap { font-family:ui-monospace,monospace; font-size:11px; color:var(--soft); }
ul { color:var(--soft); font-family:ui-sans-serif,system-ui,sans-serif; font-size:0.9rem; }
"""


def _e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _safe_filename(person_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", person_id)[:120]


def _fmt_score(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def key_achievement(person: Person) -> str:
    best = None
    for profile in person.profiles:
        if profile.rating is None:
            continue
        if best is None or profile.rating > best.rating:
            best = profile
    if best is None:
        if person.profiles:
            p = person.profiles[0]
            return f"{p.platform}:{p.handle}"
        return ""
    rank = ""
    if best.rank_pct is not None:
        rank = f" · p{best.rank_pct}"
    return f"{best.rating:g} {best.platform}{rank}"


def domains(person: Person) -> list[str]:
    seen: list[str] = []
    for profile in person.profiles:
        if profile.platform not in seen:
            seen.append(profile.platform)
    return seen


def why_now(person: Person) -> str:
    mark = key_achievement(person)
    surfaces = ", ".join(sorted(person.links)) or "no extra professional surface yet"
    return (
        f"{person.display_name or person.id} — {mark}. "
        f"Addressable via {surfaces}. Still looks IC-shaped from published bios."
    )


def outreach_draft(person: Person) -> str:
    mark = key_achievement(person)
    name = person.display_name or person.profiles[0].handle if person.profiles else person.id
    return (
        f"{name}: {mark} is on the public record, along with the links you chose to publish. "
        f"If you're even slightly curious about turning that craft into a company, "
        f"a human would like to send a short brief — no pitch deck."
    )


def _profile_urls(person: Person) -> list[tuple[str, str, str]]:
    """(label, url, provenance) for every candidate-published URL we will render."""
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(label: str, url: str | None, provenance: str) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        rows.append((label, url, provenance))

    for profile in person.profiles:
        add(
            f"{profile.platform} profile",
            profile.url,
            f"{profile.platform} profile URL for handle {profile.handle} (fetched from the public profile).",
        )
        for link in profile.profile_links:
            add(
                f"{profile.platform} self-link",
                link,
                f"Listed on {profile.platform} profile ({profile.handle}) in a bio/links field the candidate published.",
            )
    for kind, url in person.links.items():
        add(kind, url, f"Resolved as {kind} from a candidate-published self-link (see evidence).")
    return rows


def render_dossier(person: Person, scores: Scores | None) -> str:
    scores = scores or Scores(person_id=person.id)
    points = collect_history(person.profiles)
    spark = sparkline_svg(points)
    if spark:
        first, last = points[0][0], points[-1][0]
        last_v = points[-1][1]
        spark_block = spark + f'<p class="cap">{_e(first)} → {_e(last)} · last {last_v:g}</p>'
    else:
        spark_block = (
            '<p class="cap">No rating history on file — trajectory used the '
            "account-age heuristic (or is still unscored).</p>"
        )

    achieve = []
    for profile in person.profiles:
        pct = f" · p{profile.rank_pct}" if profile.rank_pct is not None else ""
        rating = f"{profile.rating:g}" if profile.rating is not None else "—"
        href = f'<a href="{_e(profile.url)}">profile</a>' if profile.url else ""
        achieve.append(
            f'<div class="row"><div>{_e(profile.platform)}</div>'
            f"<div>{_e(rating)}{_e(pct)}<br>@{_e(profile.handle)}</div>"
            f"<div>{href}</div></div>"
        )

    url_rows = _profile_urls(person)
    reach = "".join(
        f'<div><a href="{_e(url)}">{_e(label)}</a> — {_e(url)}</div>' for label, url, _ in url_rows
    )
    # Evidence appendix: Person.evidence is the source of truth (links dict
    # keeps only one personal_site). Then one provenance line per URL shown.
    evidence_items = [_e(line) for line in person.evidence]
    for _label, url, provenance in url_rows:
        evidence_items.append(_e(f"{url} — {provenance}"))
    evidence_html = "".join(f"<li>{item}</li>" for item in evidence_items) or "<li>No resolved identity links.</li>"

    location = person.country or "—"
    flags = ", ".join(scores.flags) if scores.flags else "none"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Dossier — {_e(person.display_name or person.id)}</title>
<style>{CSS}</style>
</head>
<body>
<article class="wrap">
<h1>{_e(person.display_name or person.id)}</h1>
<p class="meta">{_e(location)} · id {_e(person.id)} · flags {_e(flags)}</p>
<p class="why">{_e(why_now(person))}</p>
<div class="scores">
  <div><div class="lbl">Outlierness</div><div class="val">{_e(_fmt_score(scores.outlierness))}</div></div>
  <div><div class="lbl">Trajectory</div><div class="val">{_e(_fmt_score(scores.trajectory))}</div></div>
  <div><div class="lbl">Addressability</div><div class="val">{_e(_fmt_score(scores.addressability))}</div></div>
  <div><div class="lbl">Composite</div><div class="val">{_e(_fmt_score(scores.composite))}</div></div>
</div>
<h2>Achievements</h2>
{''.join(achieve) or '<p class="cap">No platform profiles.</p>'}
<h2>Trajectory</h2>
{spark_block}
<h2>Addressability</h2>
<div class="meta">Where they published a way to reach them. LinkedIn is a stored URL — not scraped.</div>
{reach or '<p class="cap">No self-published URLs.</p>'}
<h2>Outreach angle</h2>
<div class="draft"><strong>{DRAFT_LABEL}</strong>{_e(outreach_draft(person))}</div>
<h2>Evidence appendix</h2>
<ul>{evidence_html}</ul>
<p class="cap">Every link above was published by the candidate. We index disclosure; we do not unmask anyone. There is no send button.</p>
</article>
</body>
</html>
"""


def write_dossier(person: Person, scores: Scores | None, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    dest_dir = out_dir / "dossiers"
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{_safe_filename(person.id)}.html"
    path.write_text(render_dossier(person, scores), encoding="utf-8")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a self-contained dossier HTML file.")
    parser.add_argument("person_id", help="Person.id as stored in SQLite")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default="out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with Database(args.db) as db:
        persons = {p.id: p for p in db.all_persons()}
        scores = {s.person_id: s for s in db.all_scores()}
    person = persons.get(args.person_id)
    if person is None:
        print(f"person {args.person_id!r} not in {args.db}", file=sys.stderr)
        return 1
    path = write_dossier(person, scores.get(args.person_id), Path(args.out))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

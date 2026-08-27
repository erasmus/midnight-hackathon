"""Dossier one-pager (issue #32).

A self-contained HTML page about one candidate, written for a human to read
and then act on themselves. The system ranks and explains; a person decides
and writes.

Three rules this file exists to enforce:

  1. **Every link shown is one the candidate published themselves**, and every
     one carries its provenance line in the evidence appendix. If we cannot say
     where a link came from, it does not appear.
  2. **Weak matches are never rendered.** Collisions we declined to link stay
     out of the document entirely -- showing them would launder a refusal into
     a suggestion.
  3. **The outreach angle is a draft for a human to edit**, labelled as such,
     and there is deliberately no send or automation capability anywhere in
     this codebase.

Usage:
    python dossier.py <person_id> [--db db.sqlite] [--out out]
"""

from __future__ import annotations

import argparse
import re
import sys
from html import escape
from pathlib import Path

from core.schema import Person, Scores
from core.sparkline import sparkline_svg

DRAFT_LABEL = "DRAFT — edit before sending"

STYLE = """
:root { color-scheme: light dark; --fg:#111; --muted:#666; --line:#e5e5e5; --bg:#fff;
        --accent:#1a4f8b; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e8e8; --muted:#9a9a9a; --line:#333; --bg:#161616; --accent:#7fb3ff; }
}
* { box-sizing: border-box; }
body { margin:0; padding:2.5rem 1.5rem; background:var(--bg); color:var(--fg);
       font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
main { max-width: 46rem; margin: 0 auto; }
h1 { font-size:1.9rem; margin:0 0 .25rem; letter-spacing:-.02em; }
h2 { font-size:.8rem; text-transform:uppercase; letter-spacing:.08em;
     color:var(--muted); margin:2.5rem 0 .75rem; font-weight:600; }
.sub { color:var(--muted); margin:0 0 .5rem; }
.why { font-size:1.05rem; margin:1rem 0 0; }
.scores { display:flex; gap:.5rem; flex-wrap:wrap; margin:1.5rem 0 0; padding:0; list-style:none; }
.scores li { border:1px solid var(--line); border-radius:.5rem; padding:.6rem .9rem; flex:1 1 7rem; }
.scores b { display:block; font-size:1.35rem; font-weight:600; }
.scores span { font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
.block { border-top:1px solid var(--line); padding:.9rem 0; }
.block h3 { margin:0 0 .25rem; font-size:1rem; }
a { color:var(--accent); }
.chart { margin:1rem 0; color:var(--accent); }
ol.evidence, ul.plain { padding-left:1.2rem; }
ol.evidence li { margin:.4rem 0; color:var(--muted); font-size:.9rem; }
.draft { border:1px dashed var(--accent); border-radius:.5rem; padding:1rem 1.15rem; }
.draft .tag { display:inline-block; font-size:.7rem; font-weight:700; letter-spacing:.08em;
              color:var(--accent); margin-bottom:.5rem; }
.flags span { display:inline-block; border:1px solid var(--line); border-radius:1rem;
              padding:.15rem .6rem; font-size:.75rem; color:var(--muted); margin-right:.3rem; }
.excluded { border:1px solid var(--line); border-left:3px solid var(--accent);
            padding:.8rem 1rem; border-radius:.25rem; }
footer { margin-top:3rem; color:var(--muted); font-size:.8rem; border-top:1px solid var(--line);
         padding-top:1rem; }
"""


def _best_profile(person: Person):
    if not person.profiles:
        return None
    return max(person.profiles, key=lambda p: (p.rank_pct or 0, p.rating or 0))


def why_now(person: Person, scores: Scores) -> str:
    """One line: what makes this person interesting right now."""
    best = _best_profile(person)
    if best is None:
        return "No platform record available."
    bits = []
    if best.rank_pct is not None:
        bits.append(f"top {100 - best.rank_pct:.2f}% on {best.platform}")
    elif best.rating is not None:
        bits.append(f"{best.platform} rating {best.rating:g}")
    if scores.trajectory is not None and scores.trajectory >= 60:
        bits.append("with a rising trajectory")
    if person.birth_year:
        bits.append(f"born {person.birth_year}")
    return "; ".join(bits) + "." if bits else "No summary available."


def outreach_angle(person: Person, scores: Scores) -> str:
    """Two sentences referencing their actual work. A draft, for a human."""
    best = _best_profile(person)
    name = (person.display_name or "").split()[0] if person.display_name else "they"
    if best is None:
        return (
            f"There is no verified platform record for {name} yet. "
            "Confirm the achievement before reaching out."
        )
    what = f"{best.platform}"
    if best.rating is not None:
        what += f" (rating {best.rating:g})"
    detail = (
        f"their standing on {what}"
        if best.rank_pct is None
        else f"their top {100 - best.rank_pct:.2f}% standing on {what}"
    )
    return (
        f"Open by referencing {detail} — something they earned and published themselves. "
        f"Ask what problem they would work on next if resources were not the constraint."
    )


def _achievement_blocks(person: Person) -> str:
    blocks = []
    for profile in sorted(person.profiles, key=lambda p: p.platform):
        line = []
        title = (profile.raw or {}).get("title")
        if title:
            line.append(escape(str(title)))
        if profile.rating is not None:
            line.append(f"rating {profile.rating:g}")
        if profile.rank_pct is not None:
            line.append(f"top {100 - profile.rank_pct:.2f}%")
        link = (
            f'<a href="{escape(profile.url)}">{escape(profile.url)}</a>'
            if profile.url
            else ""
        )
        blocks.append(
            f'<div class="block"><h3>{escape(profile.platform)}</h3>'
            f'<div class="sub">{escape(" · ".join(line)) or "—"}</div>{link}</div>'
        )
    return "".join(blocks)


def _sparkline(person: Person) -> str:
    for profile in person.profiles:
        svg = sparkline_svg(profile.rating_history)
        if svg:
            return (
                f'<h2>Trajectory · {escape(profile.platform)}</h2>'
                f'<div class="chart">{svg}</div>'
            )
    return ""


def _addressability(person: Person) -> str:
    if not person.links:
        return "<p class='sub'>No self-published professional surface found.</p>"
    items = "".join(
        f'<li><b>{escape(kind)}</b> — <a href="{escape(url)}">{escape(url)}</a></li>'
        for kind, url in sorted(person.links.items())
    )
    return f'<ul class="plain">{items}</ul>'


def _evidence(person: Person) -> str:
    if not person.evidence:
        return "<p class='sub'>No resolved links, so nothing to justify.</p>"
    items = "".join(f"<li>{escape(item)}</li>" for item in person.evidence)
    return f'<ol class="evidence">{items}</ol>'


def _exclusion(scores: Scores) -> str:
    if not scores.excluded:
        return ""
    reasons = "".join(f"<li>{escape(r)}</li>" for r in scores.exclusion_reasons)
    return (
        '<h2>Excluded from the shortlist</h2>'
        f'<div class="excluded"><ul class="plain">{reasons}</ul></div>'
    )


def _score_tile(label: str, value) -> str:
    shown = "—" if value is None else f"{value:g}"
    return f"<li><b>{shown}</b><span>{escape(label)}</span></li>"


def render_dossier(person: Person, scores: Scores) -> str:
    """The complete self-contained HTML page for one candidate."""
    name = escape(person.display_name or person.id)
    meta = " · ".join(
        filter(None, [escape(person.country or ""), str(person.birth_year or "")])
    )
    flags = (
        '<div class="flags">'
        + "".join(f"<span>{escape(f)}</span>" for f in scores.flags)
        + "</div>"
        if scores.flags
        else ""
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} — candidate dossier</title>
<style>{STYLE}</style></head>
<body><main>
<h1>{name}</h1>
<p class="sub">{meta or "&nbsp;"}</p>
<p class="why">{escape(why_now(person, scores))}</p>
{flags}
<ul class="scores">
{_score_tile("outlierness", scores.outlierness)}
{_score_tile("trajectory", scores.trajectory)}
{_score_tile("addressability", scores.addressability)}
{_score_tile("composite", scores.composite)}
</ul>
{_exclusion(scores)}
<h2>Achievements</h2>
{_achievement_blocks(person)}
{_sparkline(person)}
<h2>Where to reach them</h2>
{_addressability(person)}
<h2>Suggested outreach angle</h2>
<div class="draft"><span class="tag">{escape(DRAFT_LABEL)}</span>
<p>{escape(outreach_angle(person, scores))}</p></div>
<h2>Evidence appendix</h2>
<p class="sub">Provenance of every identity link shown above. Each line names
the platform and field the link was published in.</p>
{_evidence(person)}
<footer>Generated from public, self-published records. Links are ones the
candidate published themselves. This document ranks and explains; a person
decides and writes.</footer>
</main></body></html>
"""


def _safe_filename(person_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", person_id).strip("-") or "dossier"


def write_dossier(person: Person, scores: Scores, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"dossier-{_safe_filename(person.id)}.html"
    path.write_text(render_dossier(person, scores), encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render a candidate dossier.")
    parser.add_argument("person_id", help="Person id, e.g. codeforces:ecnerwala")
    parser.add_argument("--db", default="db.sqlite")
    parser.add_argument("--out", default="out")
    args = parser.parse_args(argv)

    from core.db import Database

    db = Database(args.db)
    person = next((p for p in db.all_persons() if p.id == args.person_id), None)
    if person is None:
        print(f"No person {args.person_id!r} in {args.db}", file=sys.stderr)
        return 1
    scores = next(
        (s for s in db.all_scores() if s.person_id == args.person_id),
        Scores(person_id=args.person_id),
    )
    path = write_dossier(person, scores, args.out)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# midnight-hackathon
Entry for TechBBQ After-after-party Hack &amp; Chill

## Run

```bash
pip install -r requirements.txt
python pipeline.py                    # full run -> db.sqlite
python pipeline.py --skip-enrich      # any stage is independently skippable
python pipeline.py --github-for 50    # opt in to GitHub handle-reuse matching
python pipeline.py --no-fide-join     # skip the ~14MB FIDE rating list download
python -m pytest                      # tests (network-free)
```

## Layout

| Path | What |
|---|---|
| `pipeline.py` | orchestrator: adapters → normalize → resolve → enrich → score → rank → persist → outputs |
| `core/schema.py` | `RawProfile`, `Person`, `Scores` (spec §3) |
| `core/db.py` | SQLite, idempotent upserts on `(platform, handle)` / `person.id` |
| `core/http.py` | the **only** way to make an HTTP request: per-host ≥1s spacing, disk cache, retry-once on 5xx |
| `adapters/` | one module per source, each exposing `fetch_top(n) -> list[RawProfile]` |
| `core/links.py` | self-link extraction + classification; every link carries evidence |
| `core/github_match.py` | handle reuse, accepted only with a corroborating signal |
| `core/fide_join.py` | title + name join against the official FIDE list |
| `core/resolve.py` | the merge rule: three sanctioned mechanisms, one `_union` |
| `core/{normalize,enrich,score,outputs}.py`, `dossier.py` | stage stubs, filled in by Epics 4–6 |

## Adding an adapter

Drop a module in `adapters/` exposing `fetch_top(n)`. It is auto-discovered by
`pipeline.py`; use `core.http.get_json` / `get_html` so the rate limit and cache
apply. An adapter that raises is logged and skipped — it will not sink the run.

## The merge rule

Two profiles become one person **only** via: a self-published link from one
profile to the other, corroborated GitHub handle reuse, or the FIDE join
(exact title + name similarity ≥ 0.9). Never a shared name, never a bare
handle collision.

An uncorroborated GitHub collision is stored as a `weak_match` and never
surfaced — kept only so we can say honestly how many we declined to link.
Every accepted link carries a human-readable evidence string naming the
source platform and field.

GitHub matching is **off by default** (`--github-for N` to enable):
unauthenticated GitHub allows 60 requests/hour. Set `GITHUB_TOKEN` for 5000.

## Age verification

`birth_year` comes from exactly one place: the official FIDE monthly rating
list, joined on exact title plus name similarity ≥ 0.9. Near misses (0.8–0.9)
are recorded as near misses and left unjoined. Ambiguous FIDE entries — two
titled players sharing a name — are refused outright rather than guessed.

Everyone else has no verified age, which Epic 5 must flag as `age_unknown`
rather than assume.

# midnight-hackathon
Entry for TechBBQ After-after-party Hack &amp; Chill

## Run

```bash
pip install -r requirements.txt
python pipeline.py                 # full run -> db.sqlite
python pipeline.py --skip-enrich   # any stage is independently skippable
python -m pytest                   # tests
```

## Layout

| Path | What |
|---|---|
| `pipeline.py` | orchestrator: adapters → normalize → resolve → enrich → score → rank → persist → outputs |
| `core/schema.py` | `RawProfile`, `Person`, `Scores` (spec §3) |
| `core/db.py` | SQLite, idempotent upserts on `(platform, handle)` / `person.id` |
| `core/http.py` | the **only** way to make an HTTP request: per-host ≥1s spacing, disk cache, retry-once on 5xx |
| `adapters/` | one module per source, each exposing `fetch_top(n) -> list[RawProfile]` |
| `core/{normalize,resolve,enrich,score,outputs}.py`, `dossier.py` | stage stubs, filled in by Epics 2–6 |

## Adding an adapter

Drop a module in `adapters/` exposing `fetch_top(n)`. It is auto-discovered by
`pipeline.py`; use `core.http.get_json` / `get_html` so the rate limit and cache
apply. An adapter that raises is logged and skipped — it will not sink the run.

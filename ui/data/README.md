# UI data contract

The demo UI reads **only** these files. It does not import Python.

| File | Written by |
|---|---|
| `shortlist.json` | Pipeline (or fixtures until then) |
| `coverage.json` | Static / deck; pipeline need not touch this |

Swap fixtures for a real run by overwriting `shortlist.json` with the same shape. Keep `fixture: true` off once data is live.

`dossier.py` should emit this JSON (top 20 `Person` records, richest fields on rank 1) rather than a second HTML template. The UI is the one-pager.

## `shortlist.json`

```json
{
  "generated_at": "ISO-8601",
  "fixture": true,
  "people": [ /* Person, ranked by composite desc */ ]
}
```

Each person matches spec §3 plus a few demo-only fields the backend can leave null:

- `why_now` — one line for the dossier header
- `outreach_draft` — two sentences, labeled draft in the UI
- `warm_paths` — string list (optional)
- `location` — derived from country / GitHub / FIDE federation

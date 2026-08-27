# Outlier Engine — demo UI

Vanilla HTML/CSS/JS. **Does not import Python.** Safe to build in parallel with adapters / `pipeline.py`.

```bash
cd ui && python3 -m http.server 8765
# open http://127.0.0.1:8765              demo (shortlist / dossier)
# open http://127.0.0.1:8765/talk.html    10-minute presentation
```

Talk deck: `talk.html`. Arrow keys / space to advance, `N` speaker notes, `F` fullscreen. Current-state slides match the repo (Codeforces + Lichess live; other stages stubbed). Planned sources are open/first-party APIs only.

`file://` will fail JSON fetch — use the server.

When the pipeline can emit a shortlist, overwrite `data/shortlist.json` (set `"fixture": false`). Shape is in `data/README.md`. Suggested hook: `pipeline.py` writes that file; `dossier.py` can be a thin wrapper that opens this UI on a `person.id`.

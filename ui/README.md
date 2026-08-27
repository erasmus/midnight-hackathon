# Outlier Engine — demo UI

Vanilla HTML/CSS/JS. **Does not import Python.** Safe to build in parallel with adapters / `pipeline.py`.

```bash
cd ui && python3 -m http.server 8765
# open http://127.0.0.1:8765
```

`file://` will fail JSON fetch — use the server.

When the pipeline can emit a shortlist, overwrite `data/shortlist.json` (set `"fixture": false`). Shape is in `data/README.md`. Suggested hook: `pipeline.py` writes that file; `dossier.py` can be a thin wrapper that opens this UI on a `person.id`.

"""Local scoring explorer (GUI).

    python app.py            # http://127.0.0.1:8000

Stdlib only -- `http.server` and `sqlite3`. A hackathon demo should not depend
on a `pip install` succeeding on someone else's laptop.

The important property: **this does not reimplement scoring**. It loads the
people the pipeline already resolved, then calls the same `core.score`
functions with a `ScoringConfig` built from the sliders. What you see on screen
is the code path that wrote `shortlist.csv`, not a parallel implementation that
could drift from it.

Binds loopback only: this holds real people's data and must not be reachable
from conference wifi.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from core.db import Database
from core.schema import Scores
from core.score import DEFAULT_WEIGHTS, ScoringConfig, rank, score_person

HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _number(values: dict, key: str, fallback: float) -> float:
    """Query params come from a URL, so treat every one as hostile."""
    try:
        return float(values.get(key, [fallback])[0])
    except (TypeError, ValueError):
        return fallback


def _flag(values: dict, key: str, fallback: bool) -> bool:
    raw = values.get(key, [None])[0]
    if raw is None:
        return fallback
    return raw.lower() in ("1", "true", "yes", "on")


class Explorer:
    """Holds the resolved people in memory and re-scores them on demand."""

    def __init__(self, db_path: str | Path):
        db = Database(db_path)
        try:
            self.persons = db.all_persons()
        finally:
            db.close()
        self._by_id = {p.id: p for p in self.persons}

    def person(self, person_id: str):
        return self._by_id.get(person_id)

    def score(
        self,
        w_out: float = None,
        w_traj: float = None,
        w_addr: float = None,
        min_age: float = None,
        strict_young: bool = True,
        require_surface: bool = True,
    ) -> dict:
        weights = {
            "outlierness": DEFAULT_WEIGHTS["outlierness"] if w_out is None else w_out,
            "trajectory": DEFAULT_WEIGHTS["trajectory"] if w_traj is None else w_traj,
            "addressability": DEFAULT_WEIGHTS["addressability"] if w_addr is None else w_addr,
        }
        config = ScoringConfig(
            weights=weights,
            min_age=int(min_age) if min_age is not None else ScoringConfig().min_age,
            strict_young_platform=strict_young,
            require_surface=require_surface,
        )

        scored = [(p, score_person(p, config)) for p in self.persons]
        order = {s.person_id: i for i, s in enumerate(rank([s for _, s in scored]))}
        scored.sort(key=lambda pair: order[pair[1].person_id])

        rows = [self._row(person, scores) for person, scores in scored]
        passed = sum(1 for _, s in scored if not s.excluded)
        return {"total": len(rows), "passed": passed,
                "refused": len(rows) - passed, "rows": rows}

    @staticmethod
    def _row(person, scores: Scores) -> dict:
        best = max(
            person.profiles,
            key=lambda p: (p.rank_pct or 0, p.rating or 0),
            default=None,
        )
        return {
            "person_id": person.id,
            "name": person.display_name or person.id,
            "country": person.country or "",
            "birth_year": person.birth_year or "",
            "platforms": sorted({p.platform for p in person.profiles}),
            "headline": (
                f"{best.platform} · {best.rating:g}" if best and best.rating else
                (best.platform if best else "")
            ),
            "outlierness": scores.outlierness,
            "trajectory": scores.trajectory,
            "addressability": scores.addressability,
            "composite": scores.composite,
            "flags": scores.flags,
            "excluded": scores.excluded,
            "exclusion_reasons": scores.exclusion_reasons,
            "links": person.links,
            "evidence_count": len(person.evidence),
        }


def make_handler(explorer: Explorer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep the demo console quiet
            pass

        def _send(self, status: int, body: str, content_type: str):
            self.close_connection = True
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802 - http.server's interface
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/":
                return self._send(200, PAGE, "text/html")

            if path == "/api/score":
                summary = explorer.score(
                    w_out=_number(query, "w_out", None) if "w_out" in query else None,
                    w_traj=_number(query, "w_traj", None) if "w_traj" in query else None,
                    w_addr=_number(query, "w_addr", None) if "w_addr" in query else None,
                    min_age=_number(query, "min_age", None) if "min_age" in query else None,
                    strict_young=_flag(query, "young_strict", True),
                    require_surface=_flag(query, "require_surface", True),
                )
                return self._send(200, json.dumps(summary), "application/json")

            if path.startswith("/api/dossier/"):
                person_id = unquote(path[len("/api/dossier/"):])
                person = explorer.person(person_id)
                if person is None:
                    return self._send(404, "Unknown person", "text/plain")
                from dossier import render_dossier

                scores = score_person(person)
                return self._send(200, render_dossier(person, scores), "text/html")

            return self._send(404, "Not found", "text/plain")

    return Handler


def build_server(db_path: str | Path, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    explorer = Explorer(db_path)
    return ThreadingHTTPServer((HOST, port), make_handler(explorer))


def _number_or_none(values, key):  # pragma: no cover - helper kept for clarity
    return _number(values, key, None) if key in values else None


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Extraordinary People — scoring explorer</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ctext y='13' font-size='13'%3E%E2%97%89%3C/text%3E%3C/svg%3E">
<style>
:root { color-scheme: light dark; --fg:#111; --muted:#6b6b6b; --line:#e3e3e3;
        --bg:#fbfbfb; --panel:#fff; --accent:#1a4f8b; --warn:#8b3a1a; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e8e8; --muted:#9a9a9a; --line:#2e2e2e; --bg:#141414;
          --panel:#1b1b1b; --accent:#7fb3ff; --warn:#ff9e7f; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5
       -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
header { padding:1.1rem 1.5rem; border-bottom:1px solid var(--line);
         display:flex; align-items:baseline; gap:1.5rem; flex-wrap:wrap; }
h1 { font-size:1.05rem; margin:0; letter-spacing:-.01em; }
.counts { display:flex; gap:1.25rem; font-variant-numeric:tabular-nums; }
.counts b { font-size:1.35rem; font-weight:600; display:block; line-height:1.1; }
.counts span { font-size:.7rem; text-transform:uppercase; letter-spacing:.07em;
               color:var(--muted); }
.counts .pass b { color:var(--accent); }
.counts .refuse b { color:var(--warn); }
main { display:grid; grid-template-columns:16rem minmax(0,1fr); gap:0;
       min-height:calc(100vh - 5rem); }
main > section { min-width:0; }
/* Wide content scrolls inside its own container; the page body never does. */
#table { overflow-x:auto; }
aside { padding:1.25rem; border-right:1px solid var(--line); }
aside h2 { font-size:.7rem; text-transform:uppercase; letter-spacing:.08em;
           color:var(--muted); margin:1.5rem 0 .6rem; }
aside h2:first-child { margin-top:0; }
label { display:block; margin:.7rem 0; font-size:.82rem; }
label .v { float:right; color:var(--muted); font-variant-numeric:tabular-nums; }
input[type=range] { width:100%; accent-color:var(--accent); }
input[type=number], input[type=search] { width:100%; padding:.4rem .5rem;
  border:1px solid var(--line); border-radius:.35rem; background:var(--panel);
  color:var(--fg); font:inherit; }
.toggle { display:flex; align-items:center; gap:.5rem; margin:.6rem 0; }
button.reset { margin-top:1rem; width:100%; padding:.45rem; border:1px solid var(--line);
  background:var(--panel); color:var(--fg); border-radius:.35rem; cursor:pointer; }
.tabs { display:flex; gap:.4rem; padding:.9rem 1.25rem .4rem; }
.tabs button { border:1px solid var(--line); background:var(--panel); color:var(--muted);
  padding:.3rem .8rem; border-radius:1rem; cursor:pointer; font:inherit; font-size:.8rem; }
.tabs button[aria-pressed=true] { color:var(--fg); border-color:var(--accent); }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th { text-align:left; font-size:.68rem; text-transform:uppercase; letter-spacing:.07em;
     color:var(--muted); font-weight:600; padding:.5rem .6rem; position:sticky; top:0;
     background:var(--bg); border-bottom:1px solid var(--line); }
td { padding:.5rem .6rem; border-bottom:1px solid var(--line); }
tbody tr { cursor:pointer; }
tbody tr:hover { background:var(--panel); }
tbody tr.sel { background:var(--panel); box-shadow:inset 3px 0 0 var(--accent); }
tr.out td:nth-child(2) { color:var(--muted); }
.bar { height:.4rem; background:var(--line); border-radius:.2rem; overflow:hidden; min-width:3rem; }
.bar i { display:block; height:100%; background:var(--accent); }
.tag { display:inline-block; font-size:.68rem; color:var(--muted);
       border:1px solid var(--line); border-radius:1rem; padding:0 .45rem; margin-right:.2rem; }
/* Exclusion reasons are full sentences; without a clamp they blow the table
   out sideways and each row becomes a paragraph. Full text stays on hover. */
td:last-child { max-width:20rem; }
.why { color:var(--warn); font-size:.75rem; margin-top:.2rem;
       display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
       overflow:hidden; }
table { table-layout:auto; }
td:nth-child(2) { min-width:11rem; }
#panel { position:fixed; inset:0 0 0 auto; width:min(46rem,60vw); background:var(--panel);
  border-left:1px solid var(--line); transform:translateX(100%); transition:transform .18s ease;
  display:flex; flex-direction:column; z-index:10; }
#panel.open { transform:none; }
#panel header { justify-content:space-between; }
#panel iframe { flex:1; border:0; width:100%; background:var(--panel); }
#panel button { border:1px solid var(--line); background:transparent; color:var(--fg);
  border-radius:.35rem; padding:.25rem .7rem; cursor:pointer; font:inherit; }
.empty { padding:3rem 1.5rem; color:var(--muted); }
</style></head>
<body>
<header>
  <h1>Extraordinary People — scoring explorer</h1>
  <div class="counts">
    <div><b id="c-total">—</b><span>scored</span></div>
    <div class="pass"><b id="c-pass">—</b><span>pass filters</span></div>
    <div class="refuse"><b id="c-refuse">—</b><span>refused</span></div>
  </div>
</header>
<main>
  <aside>
    <h2>Weights</h2>
    <label>Outlierness <span class="v" id="v-out">0.45</span>
      <input type="range" id="w_out" min="0" max="1" step="0.05" value="0.45"></label>
    <label>Trajectory <span class="v" id="v-traj">0.30</span>
      <input type="range" id="w_traj" min="0" max="1" step="0.05" value="0.30"></label>
    <label>Addressability <span class="v" id="v-addr">0.25</span>
      <input type="range" id="w_addr" min="0" max="1" step="0.05" value="0.25"></label>

    <h2>Hard filters</h2>
    <label>Age floor <input type="number" id="min_age" min="0" max="99" value="18"></label>
    <div class="toggle"><input type="checkbox" id="young_strict" checked>
      <label for="young_strict" style="margin:0">Exclude unverifiable age on young-skewing platforms</label></div>
    <div class="toggle"><input type="checkbox" id="require_surface" checked>
      <label for="require_surface" style="margin:0">Require a professional surface</label></div>

    <h2>Search</h2>
    <input type="search" id="q" placeholder="name or platform">
    <button class="reset" id="reset">Reset to spec defaults</button>
  </aside>
  <section>
    <div class="tabs">
      <button data-view="pass" aria-pressed="true">Shortlist</button>
      <button data-view="all" aria-pressed="false">All</button>
      <button data-view="out" aria-pressed="false">Refused</button>
    </div>
    <div id="table"></div>
  </section>
</main>
<div id="panel"><header><b id="p-name"></b><button id="close">Close</button></header>
<iframe id="frame" title="dossier"></iframe></div>
<script>
const $ = s => document.querySelector(s);
let view = "pass", data = null;

function params() {
  const p = new URLSearchParams();
  for (const k of ["w_out","w_traj","w_addr","min_age"]) p.set(k, $("#"+k).value);
  p.set("young_strict", $("#young_strict").checked);
  p.set("require_surface", $("#require_surface").checked);
  return p.toString();
}

async function refresh() {
  for (const [id,el] of [["v-out","w_out"],["v-traj","w_traj"],["v-addr","w_addr"]])
    $("#"+id).textContent = Number($("#"+el).value).toFixed(2);
  const res = await fetch("/api/score?" + params());
  data = await res.json();
  $("#c-total").textContent = data.total;
  $("#c-pass").textContent = data.passed;
  $("#c-refuse").textContent = data.refused;
  draw();
}

function draw() {
  const q = $("#q").value.trim().toLowerCase();
  let rows = data.rows;
  if (view === "pass") rows = rows.filter(r => !r.excluded);
  if (view === "out") rows = rows.filter(r => r.excluded);
  if (q) rows = rows.filter(r =>
    r.name.toLowerCase().includes(q) || r.platforms.join(" ").includes(q));

  if (!rows.length) { $("#table").innerHTML =
    '<p class="empty">Nothing matches. Loosen a filter on the left.</p>'; return; }

  const max = Math.max(...rows.map(r => r.composite || 0), 1);
  $("#table").innerHTML = `<table><thead><tr>
    <th>#</th><th>Name</th><th>Achievement</th><th>Composite</th>
    <th>Out</th><th>Traj</th><th>Addr</th><th>Notes</th></tr></thead><tbody>` +
    rows.map((r,i) => `<tr data-id="${encodeURIComponent(r.person_id)}"
      data-name="${esc(r.name)}" class="${r.excluded ? "out" : ""}">
      <td>${i+1}</td><td><b>${esc(r.name)}</b>${r.birth_year ? " · "+r.birth_year : ""}</td>
      <td>${esc(r.headline)}</td>
      <td><div class="bar"><i style="width:${(100*(r.composite||0)/max).toFixed(0)}%"></i></div>
          ${(r.composite ?? 0).toFixed(1)}</td>
      <td>${(r.outlierness ?? 0).toFixed(1)}</td>
      <td>${(r.trajectory ?? 0).toFixed(1)}</td>
      <td>${r.addressability ?? 0}</td>
      <td>${r.flags.map(f=>`<span class="tag">${esc(f)}</span>`).join("")}
          ${r.excluded ? `<div class="why" title="${esc(r.exclusion_reasons.join(" · "))}">${esc(r.exclusion_reasons[0]||"")}</div>` : ""}</td>
    </tr>`).join("") + "</tbody></table>";

  document.querySelectorAll("tbody tr").forEach(tr => tr.onclick = () => {
    document.querySelectorAll("tbody tr").forEach(x => x.classList.remove("sel"));
    tr.classList.add("sel");
    $("#p-name").textContent = tr.dataset.name;
    $("#frame").src = "/api/dossier/" + tr.dataset.id;
    $("#panel").classList.add("open");
  });
}

const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  view = b.dataset.view;
  document.querySelectorAll(".tabs button").forEach(x =>
    x.setAttribute("aria-pressed", x === b));
  draw();
});
["w_out","w_traj","w_addr","min_age","young_strict","require_surface"]
  .forEach(id => $("#"+id).oninput = refresh);
$("#q").oninput = draw;
$("#close").onclick = () => $("#panel").classList.remove("open");
$("#reset").onclick = () => {
  $("#w_out").value = 0.45; $("#w_traj").value = 0.30; $("#w_addr").value = 0.25;
  $("#min_age").value = 18; $("#young_strict").checked = true;
  $("#require_surface").checked = true; refresh();
};
refresh();
</script></body></html>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Local scoring explorer.")
    parser.add_argument("--db", default="db.sqlite")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    httpd = build_server(args.db, args.port)
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"Scoring explorer on http://{host}:{port}  (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

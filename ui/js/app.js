function sparkline(el, series) {
  if (!el) return;
  if (!series || series.length < 2) {
    el.innerHTML = '<p class="spark-caption">No rating history on file — trajectory used the account-age heuristic.</p>';
    return;
  }
  const vals = series.map(([, v]) => v);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const w = 640;
  const h = 88;
  const pad = 6;
  const span = max - min || 1;
  const pts = vals
    .map((v, i) => {
      const x = pad + (i / (vals.length - 1)) * (w - pad * 2);
      const y = h - pad - ((v - min) / span) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const first = series[0][0];
  const last = series[series.length - 1][0];
  const lastV = vals[vals.length - 1];
  el.innerHTML = `
    <svg class="spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="Rating history">
      <polyline fill="none" stroke="#9a6b1f" stroke-width="2" points="${pts}" />
    </svg>
    <p class="spark-caption">${first} → ${last} · last ${lastV}</p>
  `;
}

function platformLabel(p) {
  return {
    codeforces: "Codeforces",
    kaggle: "Kaggle",
    lichess: "Lichess",
    fide: "FIDE",
    metaculus: "Metaculus",
    openalex: "OpenAlex",
    ctftime: "CTFtime",
  }[p] || p;
}

function achievementLine(profile) {
  const name = profile.metric_name.replace(/_/g, " ");
  const rank = profile.rank != null ? ` · rank ${profile.rank}` : "";
  const pct = profile.percentile != null ? ` · p${profile.percentile}` : "";
  return `${profile.metric_value} ${name}${rank}${pct}`;
}

function domainsOf(person) {
  const set = new Set(person.profiles.map((p) => platformLabel(p.platform)));
  return [...set];
}

function sortPeople(people) {
  return [...people].sort((a, b) => b.scores.composite - a.scores.composite);
}

const state = {
  view: "shortlist",
  people: [],
  coverage: null,
  selectedId: null,
};

function navTo(view, id) {
  state.view = view;
  if (id) state.selectedId = id;
  render();
}

function renderNav() {
  const views = [
    ["shortlist", "Shortlist"],
    ["dossier", "Dossier"],
    ["coverage", "Coverage"],
    ["limitations", "Limitations"],
    ["script", "90s script"],
  ];
  return views
    .map(
      ([id, label]) =>
        `<button type="button" data-view="${id}" ${state.view === id ? 'aria-current="page"' : ""}>${label}</button>`
    )
    .join("");
}

function renderShortlist() {
  const rows = sortPeople(state.people)
    .map((p, i) => {
      const key = p.profiles[0];
      return `<tr data-id="${p.id}" tabindex="0" role="link">
        <td class="rank">${String(i + 1).padStart(2, "0")}</td>
        <td>
          <div class="name">${escapeHtml(p.canonical_name)}</div>
          <div class="achieve">${escapeHtml(p.location || "")}</div>
        </td>
        <td><div class="pills">${domainsOf(p).map((d) => `<span class="pill">${escapeHtml(d)}</span>`).join("")}</div></td>
        <td class="achieve">${escapeHtml(key ? achievementLine(key) : "")}</td>
        <td class="num">${p.scores.outlierness}</td>
        <td class="num">${p.scores.trajectory}</td>
        <td class="num">${p.scores.addressability}</td>
        <td class="num composite">${p.scores.composite.toFixed(1)}</td>
        <td class="flag">${(p.scores.flags || []).join(", ")}</td>
      </tr>`;
    })
    .join("");

  return `
    <p class="hook">The best candidates never apply.</p>
    <p class="hook-sub">They don’t know they’re founders yet. Ranked by outlierness × trajectory × addressability. Consent-by-disclosure only.</p>
    <div class="table-wrap">
      <table class="shortlist">
        <thead>
          <tr>
            <th>#</th><th>Name</th><th>Domains</th><th>Key mark</th>
            <th>Out</th><th>Traj</th><th>Addr</th><th>Σ</th><th>Flags</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderDossier() {
  const ranked = sortPeople(state.people);
  const person = ranked.find((p) => p.id === state.selectedId) || ranked[0];
  if (!person) return `<p>No people in shortlist.json</p>`;

  const history = [];
  for (const pr of person.profiles) {
    if (pr.rating_history && pr.rating_history.length) {
      history.push(...pr.rating_history.map(([d, v]) => [d, v, pr.platform]));
    }
  }
  history.sort((a, b) => a[0].localeCompare(b[0]));
  const sparkSeries = history.map(([d, v]) => [d, v]);

  const achieves = person.profiles
    .map(
      (pr) => `<div class="achieve-block">
        <div>${escapeHtml(platformLabel(pr.platform))}</div>
        <div>${escapeHtml(achievementLine(pr))}<br><span class="achieve">@${escapeHtml(pr.handle)}</span></div>
        <div><a href="${escapeHtml(pr.profile_url)}" target="_blank" rel="noopener">profile</a></div>
      </div>`
    )
    .join("");

  const links = [];
  if (person.github) links.push(`GitHub: <a href="https://github.com/${escapeHtml(person.github.login)}" target="_blank" rel="noopener">github.com/${escapeHtml(person.github.login)}</a> · ${person.github.star_sum}★ · accel ${person.github.activity_acceleration}`);
  if (person.linkedin_url) links.push(`LinkedIn (stored, not scraped): <a href="${escapeHtml(person.linkedin_url)}" target="_blank" rel="noopener">${escapeHtml(person.linkedin_url)}</a>`);
  if (person.website) links.push(`Site: <a href="${escapeHtml(person.website)}" target="_blank" rel="noopener">${escapeHtml(person.website)}</a>`);
  for (const paper of person.papers || []) {
    links.push(`Paper: <a href="${escapeHtml(paper.url)}" target="_blank" rel="noopener">${escapeHtml(paper.title)}</a> (${paper.year}, ${escapeHtml(paper.venue)})`);
  }

  const warm = (person.warm_paths || []).map((w) => `<li>${escapeHtml(w)}</li>`).join("");
  const ev = (person.evidence || []).map((e) => `<li>${escapeHtml(e)}</li>`).join("");

  return `
    <div class="dossier-chrome">
      <button type="button" class="ghost" data-view="shortlist">← Shortlist</button>
      <span class="achieve">One-pager · human decides · no send button</span>
    </div>
    <article class="paper">
      <h1>${escapeHtml(person.canonical_name)}</h1>
      <p class="meta-line">${escapeHtml(person.location || "—")} · id ${escapeHtml(person.id)}</p>
      <p class="why">${escapeHtml(person.why_now || "")}</p>
      <div class="score-row">
        <div><div class="lbl">Outlierness</div><div class="val">${person.scores.outlierness}</div></div>
        <div><div class="lbl">Trajectory</div><div class="val">${person.scores.trajectory}</div></div>
        <div><div class="lbl">Addressability</div><div class="val">${person.scores.addressability}</div></div>
        <div><div class="lbl">Composite</div><div class="val">${person.scores.composite.toFixed(1)}</div></div>
      </div>
      <h2>Achievements</h2>
      ${achieves}
      <h2>Trajectory</h2>
      <div id="spark-host"></div>
      <h2>Addressability</h2>
      <div class="reach">${links.map((l) => `<div>${l}</div>`).join("")}</div>
      ${warm ? `<p class="meta-line" style="margin-top:12px">Warm paths (suggestions)</p><ul>${warm}</ul>` : ""}
      <h2>Outreach angle</h2>
      <div class="draft">
        <strong>Draft — edit before sending. Not automated.</strong>
        ${escapeHtml(person.outreach_draft || "")}
      </div>
      <h2>Evidence appendix</h2>
      <ul class="evidence">${ev}</ul>
      <p class="meta-line">Every link above was published by the candidate. We index disclosure; we do not unmask anyone.</p>
    </article>
  `;
}

function renderCoverage() {
  const c = state.coverage;
  if (!c) return "<p>Missing coverage.json</p>";
  const row = (s, cls) =>
    `<tr>
      <td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(s.domain)}</td>
      <td>${escapeHtml(s.tier)}</td>
      <td class="${cls}">${escapeHtml(s.status)}</td>
      <td>${escapeHtml(s.metric || s.note || "")}</td>
    </tr>`;
  return `
    <p class="hook">7 adapters tonight. 22 identified. One schema.</p>
    <p class="hook-sub">The moat isn’t scraping — it’s the consented identity graph and the cross-domain normalization table.</p>
    <h2 style="font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--brass-bright)">Built</h2>
    <table class="cov-table">
      <thead><tr><th>Source</th><th>Domain</th><th>Tier</th><th>Status</th><th>Metric</th></tr></thead>
      <tbody>${c.built.map((s) => row(s, "status-built")).join("")}</tbody>
    </table>
    <h2 style="font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--brass-bright);margin-top:32px">Identified — not built</h2>
    <table class="cov-table">
      <thead><tr><th>Source</th><th>Domain</th><th>Tier</th><th>Status</th><th>Note</th></tr></thead>
      <tbody>${c.roadmap.map((s) => row(s, "status-id")).join("")}</tbody>
    </table>
    <div class="excluded">
      <h2 style="font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--brass-bright)">Excluded by design</h2>
      ${c.excluded
        .map(
          (e) => `<article><h3>${escapeHtml(e.name)}</h3><p>${escapeHtml(e.reason)}</p></article>`
        )
        .join("")}
    </div>
  `;
}

function renderLimitations() {
  return `
    <p class="hook">Say these before the judges do.</p>
    <div class="limitations">
      <article>
        <h3>Percentile normalization is a v0 heuristic</h3>
        <p>Gap 3 is a research problem. We shipped a documented first pass (see deck/normalization.md). Codeforces percentiles are exact; everything else is rank-against-published-population.</p>
      </article>
      <article>
        <h3>Handle-reuse is tuned for precision</h3>
        <p>Uncorroborated collisions are stored as weak_match and never surfaced. Recall is deliberately low. Twenty correct people beat two hundred with three errors.</p>
      </article>
      <article>
        <h3>No ground-truth backtest yet</h3>
        <p>Gap 6: the obvious next step is tracing known founders backward through these platforms. Not in tonight’s build.</p>
      </article>
      <article>
        <h3>LinkedIn is link-only</h3>
        <p>ToS. We store a self-published URL. A human opens it. There is no scrape path and no send button.</p>
      </article>
    </div>
  `;
}

function renderScript() {
  return `
    <div class="script">
      <p class="hook">Ninety seconds.</p>
      <ol>
        <li>Hook: "The best candidates never apply, because they don’t know they’re founders yet.”</li>
        <li>Shortlist: real rankings, six domains, one schema. Point at composite = 0.45·out + 0.30·traj + 0.25·addr. Mention the relevance gate.</li>
        <li>Click the #1 row. Walk achievement → sparkline → evidence appendix. “Every link here was published by the candidate themselves — we index disclosure, we don’t unmask anyone. Polymarket is on our excluded list <em>by design</em>.”</li>
        <li>Coverage tab: “7 adapters tonight, 22 identified, one schema. The moat isn’t scraping — it’s the consented identity graph and the cross-domain normalization table.”</li>
        <li>If time: Limitations tab. Don’t let judges discover the gaps.</li>
      </ol>
      <p class="hook-sub">Rehearse once against this UI. After the pipeline lands, overwrite ui/data/shortlist.json and keep the same clicks.</p>
    </div>
  `;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render() {
  document.getElementById("nav").innerHTML = renderNav();
  const main = document.getElementById("main");
  const banner = document.getElementById("banner");
  banner.classList.toggle("hidden", !window.__FIXTURE__);
  if (state.view === "shortlist") main.innerHTML = renderShortlist();
  else if (state.view === "dossier") main.innerHTML = renderDossier();
  else if (state.view === "coverage") main.innerHTML = renderCoverage();
  else if (state.view === "limitations") main.innerHTML = renderLimitations();
  else if (state.view === "script") main.innerHTML = renderScript();

  if (state.view === "dossier") {
    const person = sortPeople(state.people).find((p) => p.id === state.selectedId) || sortPeople(state.people)[0];
    const hist = [];
    if (person) {
      for (const pr of person.profiles) {
        if (pr.rating_history) hist.push(...pr.rating_history);
      }
    }
    sparkline(document.getElementById("spark-host"), hist);
  }
}

document.getElementById("nav").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-view]");
  if (btn) navTo(btn.getAttribute("data-view"));
});

document.getElementById("main").addEventListener("click", (e) => {
  const back = e.target.closest("[data-view]");
  if (back && back.tagName === "BUTTON") {
    navTo(back.getAttribute("data-view"));
    return;
  }
  const row = e.target.closest("tr[data-id]");
  if (row) {
    navTo("dossier", row.getAttribute("data-id"));
  }
});

document.getElementById("main").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const row = e.target.closest("tr[data-id]");
  if (!row) return;
  e.preventDefault();
  navTo("dossier", row.getAttribute("data-id"));
});

async function boot() {
  const [list, cov] = await Promise.all([
    fetch("data/shortlist.json").then((r) => r.json()),
    fetch("data/coverage.json").then((r) => r.json()),
  ]);
  window.__FIXTURE__ = !!list.fixture;
  state.people = list.people || [];
  state.coverage = cov;
  state.selectedId = sortPeople(state.people)[0]?.id;
  render();
}

boot().catch((err) => {
  document.getElementById("main").innerHTML = `<p>Failed to load data: ${escapeHtml(err.message)}. Serve this folder over HTTP (python3 -m http.server).</p>`;
});

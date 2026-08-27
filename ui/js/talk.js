const NOTES = [
  "One-liner only. Point at the 10-minute map. Do not use applicant-seat anecdotes.",
  "Public proof already exists. We only join when they published the join. Contrast with unmasking.",
  "Walk the five rules quickly. Linger on consent-by-disclosure and no send button.",
  "Read the flow line once. Evidence field is the trust demo.",
  "Be precise: Codeforces + Lichess fetch. Pipeline and HTTP/SQLite are real. Resolve/score are stubs. Fixture UI.",
  "Say the weights out loud. Codeforces exact; Gap 3 is documented. LinkedIn is link-only.",
  "Group the APIs. Emphasize Liquipedia = no scrape, Product Hunt = non-commercial default. GitHub is already the enricher.",
  "Polymarket / wallets / private lists — excluded by design, not a backlog item.",
  "Percentiles, low recall, no backtest, fixture banner. Say them first.",
  "Close on dossiers for humans. Switch to index.html if there is time for a click-through.",
];

const slides = [...document.querySelectorAll(".slide")];
const dots = document.getElementById("dots");
const notesBody = document.getElementById("notes-body");
const notesEl = document.getElementById("notes");
const clockEl = document.getElementById("clock");
let i = 0;
let startedAt = Date.now();

slides.forEach((_, idx) => {
  const b = document.createElement("button");
  b.type = "button";
  b.setAttribute("aria-label", `Slide ${idx + 1}`);
  b.addEventListener("click", () => go(idx));
  dots.appendChild(b);
});

function go(n) {
  i = Math.max(0, Math.min(slides.length - 1, n));
  slides.forEach((s, idx) => {
    const on = idx === i;
    s.classList.toggle("is-active", on);
    s.hidden = !on;
  });
  [...dots.children].forEach((d, idx) => d.classList.toggle("is-on", idx === i));
  notesBody.textContent = NOTES[i] || "";
  location.hash = String(i + 1);
}

function tick() {
  const s = Math.floor((Date.now() - startedAt) / 1000);
  const m = Math.floor(s / 60);
  clockEl.textContent = `${m}:${String(s % 60).padStart(2, "0")}`;
}

document.getElementById("prev").addEventListener("click", () => go(i - 1));
document.getElementById("next").addEventListener("click", () => go(i + 1));

document.addEventListener("keydown", (e) => {
  if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(e.key)) {
    e.preventDefault();
    go(i + 1);
  } else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(e.key)) {
    e.preventDefault();
    go(i - 1);
  } else if (e.key === "Home") {
    go(0);
  } else if (e.key === "End") {
    go(slides.length - 1);
  } else if (e.key === "n" || e.key === "N") {
    notesEl.hidden = !notesEl.hidden;
  } else if (e.key === "f" || e.key === "F") {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen?.();
    else document.exitFullscreen?.();
  }
});

const fromHash = Number.parseInt(location.hash.replace("#", ""), 10);
go(Number.isFinite(fromHash) && fromHash >= 1 ? fromHash - 1 : 0);
setInterval(tick, 250);
tick();

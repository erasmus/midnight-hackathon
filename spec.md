# Outlier Engine — Build Spec

**One-liner:** A consent-first talent index that finds people with verified, exceptional performance in competitive domains, filters for those who have voluntarily linked a professional identity, scores them on outlierness × trajectory × addressability, and outputs founder-outreach dossiers.

**Hackathon scope:** 7 source adapters, 1 schema, 1 scoring function, 1 ranked shortlist, 1 polished dossier. Everything else is deck material.

---

## 1. Principles (hard constraints)

1. **Consent-by-disclosure only.** A person enters the index only if their competition profile publicly links to a real-world identity (real name field, bio link, or verifiable handle reuse). No de-anonymization, no wallet tracing, no cross-referencing to unmask pseudonyms.
2. **Age floor 18.** If birth year is available (FIDE, some olympiad lists), enforce it. If age is unknown and the platform skews young (speedrun, esports), require independent evidence of adulthood (university graduation, employment) or drop.
3. **Top-of-tail only.** Pull top-N (≤500) per platform. No bulk harvesting. Polite rate limits (≥1s between requests where no bulk endpoint exists).
4. **Relevance gate.** Raw talent alone doesn't rank. Every candidate needs at least one professional/technical surface (GitHub, LinkedIn, personal site, papers) — this is the addressability axis, and it doubles as the consent filter.
5. **Output is dossiers for humans, not automated outreach.** The system ranks and explains; a person decides and writes.

---

## 2. Architecture

```
[Adapters (7)] → [normalize] → [identity resolve (self-links only)]
    → [enrich (GitHub/OpenAlex/site)] → [score] → [rank]
    → [SQLite] → [shortlist CSV + dossier generator]
```

Single Python repo. No infra. SQLite + one `pipeline.py` orchestrator. Each adapter is a module exposing `fetch_top(n) -> list[RawProfile]`.

```
outlier-engine/
  adapters/        # kaggle.py, codeforces.py, lichess.py, metaculus.py,
                   # ctftime.py, fide.py, openalex.py
  core/
    schema.py      # dataclasses / pydantic models
    resolve.py     # self-link extraction + handle-reuse matching
    enrich.py      # GitHub + web enrichment
    score.py       # outlierness, trajectory, addressability
  pipeline.py
  dossier.py       # renders markdown/HTML one-pager
  db.sqlite
```

---

## 3. Data model

```python
class RawProfile:
    platform: str            # "codeforces"
    handle: str
    display_name: str | None # real name if platform provides it
    metric_value: float      # rating / score / medals
    metric_name: str         # "cf_rating", "kaggle_comp_medals_gold", ...
    rank: int | None         # leaderboard position
    percentile: float | None # computed vs platform population if known
    rating_history: list[tuple[date, float]]  # [] if unavailable
    profile_links: list[str] # URLs found in bio/profile fields
    country: str | None
    birth_year: int | None   # FIDE only, mostly
    profile_url: str
    fetched_at: datetime

class Person:                # post-resolution
    id: str
    canonical_name: str | None
    profiles: list[RawProfile]        # ≥1
    github: GitHubEnrichment | None
    linkedin_url: str | None          # stored, not scraped
    website: str | None
    papers: list[Paper]               # via OpenAlex
    evidence: list[str]               # human-readable provenance of every link
    scores: Scores

class Scores:
    outlierness: float       # 0–100
    trajectory: float        # 0–100
    addressability: float    # 0–100
    composite: float
    flags: list[str]         # "age_unknown", "single_source", "already_founder"
```

**Evidence field is non-negotiable.** Every identity link must record *why* we believe it ("Codeforces profile lists github.com/xyz in organization field"). This is what makes the demo trustworthy and the misidentification risk visible.

---

## 4. Adapters

Priority order. Stop wherever time runs out — first four alone make the demo.

### 4.1 Kaggle (30 min)
- **Source:** Meta Kaggle dataset (public, on Kaggle itself: `kaggle/meta-kaggle`). Download `Users.csv`, `UserAchievements.csv` once; no API needed.
- **Pull:** Competitions Grandmasters + Masters. Filter tier from `UserAchievements` (AchievementType = Competitions, Tier ≥ Master).
- **Metric:** tier + medal counts + highest rank.
- **Identity:** `Users.csv` has display name; profile pages list GitHub/LinkedIn/Twitter — fetch profile page for top candidates only (rate-limited HTML fetch) or skip and rely on name + handle reuse.
- **Gotcha:** dataset is large; stream-filter CSVs, don't load whole thing.

### 4.2 Codeforces (20 min)
- **Endpoints:** `api/user.ratedList?activeOnly=true` (whole ranked population in one call — gives you exact percentiles for free), `api/user.info?handles=...` (batch, 300+ handles per call), `api/user.rating?handle=` (full contest history per user).
- **Pull:** everyone ≥ 2400 (International Grandmaster territory) or top 500.
- **Identity:** `firstName`, `lastName`, `organization`, `country` fields exist and are often filled. Handle-reuse check against GitHub (see §5).
- **Trajectory:** `user.rating` gives dated contest results → compute climb slope directly.

### 4.3 Lichess (20 min)
- **Endpoints:** `api/player/top/200/{blitz|rapid|classical}`, `api/user/{username}` (profile incl. bio + links + `fideRating` field), `api/user/{username}/rating-history`.
- **Pull:** top 200 per time control, dedupe.
- **Identity:** bio links + declared FIDE rating → join to FIDE list (§4.6). Titled players (`title` field: GM/IM/etc.) are near-certainly real-name-resolvable via FIDE.
- **Note:** Lichess API is generous; use `Accept: application/x-ndjson` bulk endpoints where offered.

### 4.4 Metaculus (20 min)
- **Endpoints:** public JSON API; rankings page is backed by an API returning user ids + scores; `api2/users/{id}` for profiles.
- **Pull:** top ~200 by peer score / tournament ranking.
- **Identity:** many top forecasters use real names; profiles and linked essays/Twitter in bios.
- **Gotcha:** API shape has shifted between versions — budget 10 min for inspecting live responses in the browser network tab before coding.

### 4.5 CTFtime (15 min)
- **Endpoints:** `api/v1/top/{year}/` (top teams), `api/v1/teams/{id}/` (team detail).
- **Pull:** top 50 teams; members where listed.
- **Identity:** team pages link websites/GitHub orgs; individual attribution is weaker — treat hits as bonus, not core.

### 4.6 FIDE (15 min)
- **Source:** monthly rating list, downloadable TXT/XML from ratings.fide.com. No API needed — one file parse.
- **Pull:** everyone ≥ 2500, plus anyone ≥ 2300 born ≥ 1998 (young-and-rising).
- **Fields:** real name, federation, **birth year**, title. This is your age-verification oracle and your chess.com/Lichess join target.

### 4.7 OpenAlex (20 min)
- **Endpoints:** `api.openalex.org/works` and `/authors`, filters like `authors.count`, citation counts, `from_publication_date`. Fully open, no key.
- **Pull:** authors with high citation velocity and short career length (first publication ≤ 6 years ago, citations ≥ threshold) in CS/ML/bio venues.
- **Identity:** real names + institution by construction; ORCID links, often GitHub in paper artifacts.
- **Role:** both a *source* (young star researchers) and an *enricher* (does a candidate publish?).

---

## 5. Identity resolution (`resolve.py`)

Only two mechanisms. Nothing cleverer.

1. **Explicit self-links:** URLs in profile/bio fields → classify by domain (github.com, linkedin.com/in, personal domain, twitter/x). Store with evidence string.
2. **Handle reuse:** for each platform handle, check `api.github.com/users/{handle}`. Accept the match only if ≥1 corroborating signal: same display name, bio mentions the platform ("CF grandmaster", "kaggle"), or the GitHub profile links back. Uncorroborated handle collisions are discarded — record as `weak_match`, never surfaced.

FIDE join: Lichess/chess.com titled players matched by (title + name) against the FIDE file; require exact title match + fuzzy name ≥ 0.9.

**Merge rule:** two RawProfiles merge into one Person only via mechanism 1 or 2. Everything else stays separate. Precision over recall — a demo with 20 correct people beats 200 with three errors.

---

## 6. Enrichment (`enrich.py`)

For resolved Persons only (keeps API budget tiny):

- **GitHub:** `users/{login}` + `users/{login}/repos` → account age, followers, star sum, recent push activity, repo topics. Compute *activity acceleration*: commits/pushes last 6 months vs. prior baseline (events API or repo `pushed_at` distribution as cheap proxy).
- **Founder-already check:** GitHub bio/company field, personal-site title, OpenAlex affiliation containing "founder/CEO/stealth" → set `already_founder` flag (these people are *out of target* — the whole point is pre-intent).
- **LinkedIn:** store URL if self-linked; do **not** scrape (ToS). The human reads it from the dossier.

---

## 7. Scoring (`score.py`)

```
composite = 0.45 * outlierness + 0.30 * trajectory + 0.25 * addressability
```

**Outlierness (0–100):** platform percentile mapped to a shared scale. Where full population is known (Codeforces ratedList) compute exactly; elsewhere use rank-based approximation against published population sizes. Multi-domain bonus: +10 if top-1% in ≥2 unrelated domains (capped at 100). Document every mapping in one table — this table *is* Gap 3 and belongs in the deck.

**Trajectory (0–100):** from `rating_history` where available (Lichess, Codeforces): slope of rating over last 24 months, normalized by platform volatility; recency weight (active in last 90 days); GitHub activity acceleration as secondary input. No history → score from account-age-vs-rank ("reached top 100 within 2 years of account creation").

**Addressability (0–100):** GitHub with real activity = 40; LinkedIn self-link = 25; personal site = 20; papers = 15. Cap 100.

**Hard filters (before scoring):** age floor (§1.2), `already_founder` excluded, single-source-no-professional-surface excluded (the horse-rider rule).

---

## 8. Outputs

1. **`shortlist.csv`** — top 20 by composite: name, domains, key achievement, scores, links, evidence.
2. **`dossier.py` → one-pager** (markdown → HTML) for the #1 candidate:
   - Header: name, location, one-line "why now"
   - Achievement block per platform with verifiable links
   - Trajectory sparkline (rating history — matplotlib, 10 lines)
   - Addressability: where to reach them, warm-path suggestions if any
   - Evidence appendix: every identity link with provenance
   - Suggested outreach angle (2 sentences, referencing their actual work — written to be *edited by a human*, labeled as draft)
3. **Coverage roadmap table** — the other 15 sources from the research list with tier/status. Deck slide, zero code.

---

## 9. Timebox (2h, two people)

| Time | Person A | Person B |
|---|---|---|
| 0:00–0:15 | schema.py + pipeline skeleton + SQLite | Download Meta Kaggle + FIDE files |
| 0:15–0:50 | Codeforces + Lichess adapters | Kaggle + FIDE adapters |
| 0:50–1:10 | resolve.py (self-links + GitHub handle check) | Metaculus adapter (CTFtime if fast) |
| 1:10–1:30 | score.py | enrich.py (GitHub) |
| 1:30–1:50 | Run pipeline, eyeball shortlist, fix garbage | dossier.py + sparkline |
| 1:50–2:00 | Pick demo candidate, generate dossier | Coverage table + demo script |

Cut order if behind: CTFtime → Metaculus → OpenAlex → trajectory-from-GitHub (keep rating-history trajectory).

## 10. Demo script (90 seconds)

1. "35,000 applications, 35 seats — and the best candidates never apply, because they don't know they're founders yet."
2. Show the shortlist: real people, real rankings, six domains, one schema.
3. Click into the dossier: achievement → trajectory sparkline → evidence appendix. "Every link here was published by the candidate themselves — we index disclosure, we don't unmask anyone. Polymarket is on our excluded list *by design*."
4. Coverage roadmap: "7 adapters tonight, 22 identified, one schema. The moat isn't scraping — it's the consented identity graph and the cross-domain normalization table."

## 11. Known limitations (say them before judges do)

- Percentile normalization across domains is v0 heuristic (Gap 3 is a research problem; we shipped a defensible first pass).
- Handle-reuse matching tuned for precision; recall is deliberately low.
- No ground-truth validation yet — backtest against known founders' historical traces is the obvious next step (Gap 6).
- LinkedIn is link-only by ToS; human completes that step.

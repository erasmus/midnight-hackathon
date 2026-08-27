# Outlierness mapping table (Gap 3 — v0)

Documented heuristic. Codeforces is exact; all others are rank against a published (or estimated) population. This table is deck material; scoring code should cite the same numbers.

`composite = 0.45 * outlierness + 0.30 * trajectory + 0.25 * addressability`

Multi-domain bonus: **+10** if top-1% in ≥2 *unrelated* domains (chess blitz + chess rapid = one domain). Cap 100.

| Platform | Population source | Percentile method | Top-1% ≈ | Notes |
|---|---|---|---|---|
| Codeforces | `user.ratedList?activeOnly=true` | Exact rank / N | rating ~2300-band, verify live | **Exact** |
| Kaggle | Published Competitions tier counts + Meta Kaggle | Rank among Masters+ vs estimated competitor pop | GM/Master | Approx |
| Lichess | Published registered users; we only pull top 200 | Rank-based vs top-200 window, not full site | Top 200 / time control | Approx; do not treat site-wide |
| FIDE | Monthly list, standard rating | Rank among published actives ≥1400 or list N | ~2500 | Birth year = age oracle |
| Metaculus | Rankings payload size | Rank / listed forecasters | Top ~50–200 | API shape may drift |
| OpenAlex | Filter set (venue × career length) | Rank inside the pulled slice, labeled as such | High citation velocity, career ≤6y | Slice ≠ field-wide |
| CTFtime | Top 50 teams | Team rank; individuals flagged weak-attribution | Top 50 teams | Bonus source |

## Trajectory (companion constants)

| Platform | Slope window | Volatility normalizer (v0) |
|---|---|---|
| Codeforces | 24 months of contest ratings | Divide slope by ~80 rating pts / year typical IGM noise |
| Lichess | 24 months rating-history | Divide by ~60 pts / year |
| None | — | Account-age vs rank: top 100 within 2 years of creation; flag heuristic |

Recency: inactive >90 days decays trajectory (implementation detail for `score.py`).

## Addressability weights (fixed)

| Surface | Points |
|---|---|
| GitHub with real recent activity | 40 |
| LinkedIn self-link (stored only) | 25 |
| Personal site | 20 |
| Papers (OpenAlex) | 15 |
| Cap | 100 |

# Normalization table

How each platform's raw standing becomes a 0–100 score. **This table is the
contract**: every constant here has a matching constant in `core/score.py`, and
changing one without the other is a bug.

The honest summary: **one platform gives us an exact percentile. The rest are
estimates**, and they are labelled as such everywhere they appear.

## Outlierness (#27)

| Platform | Population source | Percentile method | Exact? |
|---|---|---|---|
| **Codeforces** | `api/user.ratedList?activeOnly=true` returns the *entire* rated population in one call | Rank of this rating within the full population | ✅ **Exact** |
| Lichess | None — the API exposes only the top 200 per time control | Rating mapped through the anchor curve below | ⚠️ Estimate |
| chess.com | None (adapter not built) | Same curve as Lichess | ⚠️ Estimate |
| FIDE | Full monthly list is available, but it is a rating list, not a ranked table | Rating mapped through the anchor curve below | ⚠️ Estimate |
| Kaggle | Tier + medal counts (adapter not built, #12) | Tier → percentile, to be defined with that adapter | ⚠️ Estimate |
| Metaculus | Published leaderboard size (#16) | Rank ÷ population | ⚠️ Estimate |
| OpenAlex | Citation distribution (#17) | Percentile within field | ⚠️ Estimate |
| CTFtime | Published team/player counts (#18) | Rank ÷ population | ⚠️ Estimate |

### Rating → percentile anchors

Linear interpolation between anchors; below the lowest anchor scores 0.

| Rating | Lichess / chess.com | FIDE |
|---|---|---|
| 2000 | — | 90.0 |
| 2200 | 90.0 | — |
| 2300 | — | 97.0 |
| 2400 | 97.0 | — |
| 2500 | — | 99.0 |
| 2600 | 99.0 | — |
| 2700 | — | 99.8 |
| 2800 | 99.8 | 99.95 |
| 3000 | 99.95 | — |

FIDE's curve sits ~200–300 points lower than the online curves because
over-the-board ratings are deflated relative to online blitz.

### Domains and the multi-domain bonus

The bonus is **+10 for being ≥99th percentile in two _unrelated_ domains**,
capped at 100.

| Platform | Domain |
|---|---|
| Codeforces | `competitive_programming` |
| Lichess, chess.com, FIDE | `chess` |
| Kaggle | `machine_learning` |
| Metaculus | `forecasting` |
| OpenAlex | `research` |
| CTFtime | `security` |

Lichess + FIDE is **one** domain, not two — chess blitz and chess rapid are not
two fields of excellence.

> **Known quirk:** the bonus can only fire when the person is already ≥99th
> percentile somewhere, so `best + 10` always exceeds the cap. In practice the
> bonus means "multi-domain elites score exactly 100", not "+10". Kept at +10
> to match the spec, but worth knowing before anyone tunes it.

## Trajectory (#28)

Slope of rating over the **last 24 months**, in rating points per year,
normalised per platform. 0 change → 50; `+normaliser`/year → 100;
`−normaliser`/year → 0.

| Platform | Points/year that counts as a strong rise | Why |
|---|---|---|
| Codeforces | 200 | Online CP ratings move fast |
| Lichess / chess.com | 150 | Online chess, slightly slower |
| FIDE | 50 | Over-the-board ratings move very slowly |
| *(default)* | 150 | Any platform without its own constant |

**Recency:** last data point older than **90 days** halves the score
(`INACTIVE_DECAY = 0.5`).

**Fallback** when there is no usable history: account-age-vs-standing —
reaching this standing within 730 days of account creation scores 100, decaying
with account age. Scores produced this way are flagged; see
`uses_trajectory_fallback()`.

No history *and* no account age → neutral 50, because we know nothing, and
guessing in either direction would be a fabrication.

## Addressability (#29)

| Surface | Points |
|---|---|
| GitHub **with verified recent activity** | 40 |
| LinkedIn self-link | 25 |
| Personal site | 20 |
| Papers | 15 |

Capped at 100. Twitter deliberately scores nothing — it is a broadcast channel,
not evidence of a professional surface.

> **Dependency:** "verified recent activity" requires GitHub enrichment
> (#23, Epic 4). Until that lands, activity is unknown and GitHub scores **0** —
> the conservative reading. Expect addressability to jump once #23 ships.

## Composite (#30)

```
composite = 0.45 × outlierness + 0.30 × trajectory + 0.25 × addressability
```

Excluded people are scored anyway and always sort last, so the shortlist can be
audited against what was refused. Ties break on person id, so ranking is stable
across re-runs.

## Hard filters (#26), applied before scoring

1. **Age floor 18.** Enforced on `birth_year` where known. Where unknown *and*
   the platform skews young (chess, competitive programming), the person is
   **excluded** unless enrichment supplies independent adulthood evidence.
   Excluded, not assumed adult.
2. **Already a founder** → excluded.
3. **Relevance gate.** Single source *and* no professional surface → excluded.
   Being extraordinary at one thing with no reachable professional presence is
   not something this pipeline can act on.

Excluded people are **persisted with their reasons**, never deleted.

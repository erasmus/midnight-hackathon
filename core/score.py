"""Scoring and ranking (Epic 5, issues #26-#30).

    composite = 0.45*outlierness + 0.30*trajectory + 0.25*addressability

Hard filters run **first**, and excluded people are persisted with their
reasons rather than deleted -- a shortlist you cannot audit is a shortlist you
cannot defend.

The normalization table behind `outlierness` and `trajectory` lives in
`docs/normalization.md`. Every per-platform constant in this module has a row
there; if you change one here, change it there too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from core.schema import Person, Scores

CURRENT_YEAR = datetime.now(timezone.utc).year
MIN_AGE = 18

# Platforms whose leaderboards are full of minors. On these, "we don't know
# their age" is not good enough: chess and competitive-programming tops are
# routinely teenagers, so an unknown age must be resolved, not assumed.
YOUNG_SKEWING_PLATFORMS = frozenset({"lichess", "chesscom", "fide", "codeforces"})

# Addressability weights (#29), exactly as specified.
ADDRESSABILITY_WEIGHTS = {
    "github": 40,   # only with verified activity -- see `_github_is_active`
    "linkedin": 25,
    "personal_site": 20,
    "papers": 15,
}
# A link kind that counts as "this person has a professional surface at all",
# independent of whether it scores. Twitter is deliberately absent.
PROFESSIONAL_SURFACES = frozenset(ADDRESSABILITY_WEIGHTS)


@dataclass
class FilterResult:
    excluded: bool = False
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def _platforms(person: Person) -> set[str]:
    return {p.platform for p in person.profiles}


def has_professional_surface(person: Person) -> bool:
    """Any self-published surface a human could reach them through."""
    return any(kind in person.links for kind in PROFESSIONAL_SURFACES)


def _github_is_active(person: Person) -> bool:
    """#29 requires *real activity*, not merely an account.

    Until enrichment (#23) runs, activity is unknown and GitHub scores zero.
    That is the conservative reading of the acceptance criterion: an account
    we have not looked at is not evidence that anyone can reach this person.
    """
    activity = (person.enrichment or {}).get("github_activity") or {}
    return bool(activity.get("active"))


def addressability(person: Person) -> int:
    """0-100. Doubles as the consent filter: no surface, no rank (#29)."""
    total = 0
    for kind, weight in ADDRESSABILITY_WEIGHTS.items():
        if kind not in person.links:
            continue
        if kind == "github" and not _github_is_active(person):
            continue
        total += weight
    return min(total, 100)


def _age(person: Person) -> int | None:
    if not person.birth_year:
        return None
    return CURRENT_YEAR - person.birth_year


def hard_filter(person: Person) -> FilterResult:
    """Run every gate. Collect *all* failures, not just the first (#26)."""
    result = FilterResult()

    # (a) age floor.
    age = _age(person)
    if age is not None:
        if age < MIN_AGE:
            result.excluded = True
            result.reasons.append(
                f"under {MIN_AGE}: born {person.birth_year}, age ~{age}"
            )
    else:
        result.flags.append("age_unknown")
        has_adulthood_evidence = bool(
            (person.enrichment or {}).get("adulthood_evidence")
        )
        young_platform = _platforms(person) & YOUNG_SKEWING_PLATFORMS
        if young_platform and not has_adulthood_evidence:
            result.excluded = True
            result.reasons.append(
                f"age unverifiable on young-skewing platform(s) "
                f"{sorted(young_platform)} and no independent adulthood "
                f"evidence; excluded rather than assumed adult"
            )

    # (b) already a founder.
    founder = (person.enrichment or {}).get("already_founder")
    if founder:
        result.flags.append("already_founder")
        result.excluded = True
        result.reasons.append(f"already a founder: {founder}")

    # (c) relevance gate -- the horse-rider rule. Being extraordinary at one
    # thing, with no professional surface at all, is not a signal we can act on.
    single_source = len(_platforms(person)) <= 1
    if single_source:
        result.flags.append("single_source")
    if single_source and not has_professional_surface(person):
        result.excluded = True
        result.reasons.append(
            "single source with no professional surface (no github, linkedin, "
            "personal site or papers): nothing to corroborate or act on"
        )

    return result


# ---------------------------------------------------------------------------
# #27 Outlierness
# ---------------------------------------------------------------------------

# Which *domain* a platform belongs to. The multi-domain bonus only fires
# across unrelated domains: chess blitz and chess rapid are one domain, and so
# are Lichess and FIDE. Every row is documented in docs/normalization.md.
DOMAINS = {
    "codeforces": "competitive_programming",
    "ctftime": "security",
    "kaggle": "machine_learning",
    "lichess": "chess",
    "chesscom": "chess",
    "fide": "chess",
    "metaculus": "forecasting",
    "openalex": "research",
}

MULTI_DOMAIN_BONUS = 10
TOP_PERCENTILE = 99.0

# Rating -> approximate percentile anchors for platforms that publish no
# population denominator. Linear interpolation between anchors; anything below
# the lowest anchor scores 0. These are ESTIMATES and are labelled as such in
# the normalization table -- unlike Codeforces, where the percentile is exact.
RATING_CURVES = {
    "lichess": [(2200, 90.0), (2400, 97.0), (2600, 99.0), (2800, 99.8), (3000, 99.95)],
    "chesscom": [(2200, 90.0), (2400, 97.0), (2600, 99.0), (2800, 99.8), (3000, 99.95)],
    "fide": [(2000, 90.0), (2300, 97.0), (2500, 99.0), (2700, 99.8), (2800, 99.95)],
}


def domains_of(platforms) -> set[str]:
    """The unrelated domains a set of platforms covers."""
    return {DOMAINS[p] for p in platforms if p in DOMAINS}


def _interpolate(curve, rating: float) -> float:
    if rating <= curve[0][0]:
        return 0.0
    for (lo_rating, lo_pct), (hi_rating, hi_pct) in zip(curve, curve[1:]):
        if rating <= hi_rating:
            span = hi_rating - lo_rating
            frac = (rating - lo_rating) / span if span else 0.0
            return lo_pct + frac * (hi_pct - lo_pct)
    return curve[-1][1]


def _profile_percentile(profile) -> float:
    """This profile's percentile, exact where we have the population."""
    if profile.rank_pct is not None:
        return float(profile.rank_pct)
    curve = RATING_CURVES.get(profile.platform)
    if curve and profile.rating is not None:
        return _interpolate(curve, float(profile.rating))
    return 0.0


def outlierness(person: Person) -> float:
    """0-100. The person's strongest percentile, plus a multi-domain bonus."""
    per_domain: dict[str, float] = {}
    best = 0.0
    for profile in person.profiles:
        pct = _profile_percentile(profile)
        best = max(best, pct)
        domain = DOMAINS.get(profile.platform)
        if domain:
            per_domain[domain] = max(per_domain.get(domain, 0.0), pct)

    elite_domains = [d for d, pct in per_domain.items() if pct >= TOP_PERCENTILE]
    if len(elite_domains) >= 2:
        best += MULTI_DOMAIN_BONUS

    return max(0.0, min(best, 100.0))


# ---------------------------------------------------------------------------
# #28 Trajectory
# ---------------------------------------------------------------------------

TRAJECTORY_WINDOW_DAYS = 730          # "last 24 months"
INACTIVE_DAYS = 90                    # activity window before decay applies
INACTIVE_DECAY = 0.5                  # multiplier once outside that window
NEUTRAL_TRAJECTORY = 50.0             # no signal either way

# Rating points per year that count as a "strong" rise on each platform, i.e.
# the slope that maps to the top of the scale. These are the per-platform
# volatility constants; every one has a row in docs/normalization.md.
SLOPE_NORMALISER = {
    "codeforces": 200.0,
    "lichess": 150.0,
    "chesscom": 150.0,
    "fide": 50.0,      # FIDE ratings move far more slowly than online ones
}
DEFAULT_SLOPE_NORMALISER = 150.0

# Fallback: reaching a leaderboard within this many days of account creation
# is treated as maximally fast (the "top 100 within 2 years" heuristic).
FAST_ASCENT_DAYS = 730


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _slope_score(profile, now: datetime) -> float | None:
    """Rating points per year over the window, normalised to 0-100."""
    cutoff = now - timedelta(days=TRAJECTORY_WINDOW_DAYS)
    points = []
    for entry in profile.rating_history or []:
        moment = _parse_date(entry.get("date"))
        rating = entry.get("rating")
        if moment is None or rating is None or moment < cutoff:
            continue
        points.append((moment, float(rating)))
    if len(points) < 2:
        return None

    points.sort()
    (first_at, first_rating), (last_at, last_rating) = points[0], points[-1]
    years = (last_at - first_at).days / 365.25
    if years <= 0:
        return None

    per_year = (last_rating - first_rating) / years
    normaliser = SLOPE_NORMALISER.get(profile.platform, DEFAULT_SLOPE_NORMALISER)
    # 0 change -> 50; +normaliser/yr -> 100; -normaliser/yr -> 0.
    score = NEUTRAL_TRAJECTORY * (1 + per_year / normaliser)

    days_since = (now - last_at).days
    if days_since > INACTIVE_DAYS:
        score *= INACTIVE_DECAY

    return max(0.0, min(score, 100.0))


def _ascent_score(profile, now: datetime) -> float | None:
    """No history: how fast did they reach this standing after signing up?"""
    created_ms = (profile.raw or {}).get("created_at")
    if not created_ms:
        return None
    try:
        created = datetime.fromtimestamp(float(created_ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    age_days = (now - created).days
    if age_days <= 0:
        return None
    # Younger account at the same standing => steeper ascent.
    return max(0.0, min(100.0, 100.0 * FAST_ASCENT_DAYS / max(age_days, 1)))


def trajectory(person: Person) -> float:
    """0-100. Slope where we have history, ascent heuristic where we do not."""
    now = datetime.now(timezone.utc)

    slopes = [s for s in (_slope_score(p, now) for p in person.profiles) if s is not None]
    if slopes:
        return max(slopes)

    ascents = [a for a in (_ascent_score(p, now) for p in person.profiles) if a is not None]
    if ascents:
        return max(ascents)

    return NEUTRAL_TRAJECTORY


def uses_trajectory_fallback(person: Person) -> bool:
    """True when the score came from the heuristic, not real history (#28)."""
    now = datetime.now(timezone.utc)
    return not any(_slope_score(p, now) is not None for p in person.profiles)


# ---------------------------------------------------------------------------
# #30 Composite, flags, ranking
# ---------------------------------------------------------------------------

WEIGHTS = {"outlierness": 0.45, "trajectory": 0.30, "addressability": 0.25}


def composite(outlierness_: float, trajectory_: float, addressability_: float) -> float:
    return (
        WEIGHTS["outlierness"] * outlierness_
        + WEIGHTS["trajectory"] * trajectory_
        + WEIGHTS["addressability"] * addressability_
    )


def score_person(person: Person) -> Scores:
    """Filter first, then score. Excluded people are scored and kept anyway."""
    verdict = hard_filter(person)

    out = outlierness(person)
    traj = trajectory(person)
    addr = addressability(person)

    return Scores(
        person_id=person.id,
        outlierness=round(out, 2),
        trajectory=round(traj, 2),
        addressability=addr,
        composite=round(composite(out, traj, addr), 2),
        flags=verdict.flags,
        excluded=verdict.excluded,
        exclusion_reasons=verdict.reasons,
    )


def score(persons: list[Person]) -> list[Scores]:
    return [score_person(p) for p in persons]


def rank(scores: list[Scores]) -> list[Scores]:
    """Excluded people always sort last; ties break on id so runs are stable."""
    return sorted(
        scores,
        key=lambda s: (s.excluded, -(s.composite or 0.0), s.person_id),
    )

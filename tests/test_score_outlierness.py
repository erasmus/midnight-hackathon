import pytest

from core.score import DOMAINS, MULTI_DOMAIN_BONUS, domains_of, outlierness
from core.schema import Person, RawProfile


def prof(platform="codeforces", rank_pct=None, rating=None, raw=None):
    return RawProfile(platform=platform, handle="x", rank_pct=rank_pct,
                      rating=rating, raw=raw or {})


def person(*profiles):
    return Person(id="x", profiles=list(profiles))


def test_an_exact_percentile_maps_straight_to_the_score():
    assert outlierness(person(prof(rank_pct=99.0))) == pytest.approx(99.0)


def test_a_higher_percentile_scores_higher():
    lo = outlierness(person(prof(rank_pct=90.0)))
    hi = outlierness(person(prof(rank_pct=99.9)))
    assert hi > lo


def test_the_best_platform_wins_when_several_are_present():
    p = person(prof("codeforces", rank_pct=80.0), prof("lichess", rating=2900))
    assert outlierness(p) >= 80.0


def test_a_person_with_no_signal_scores_zero():
    assert outlierness(person(prof())) == 0


def test_lichess_rating_is_approximated_against_the_published_population():
    # No denominator from the API, so rating maps through a documented curve.
    score = outlierness(person(prof("lichess", rating=2900)))
    assert 90 <= score <= 100


def test_a_weaker_lichess_rating_scores_lower():
    strong = outlierness(person(prof("lichess", rating=2900)))
    weak = outlierness(person(prof("lichess", rating=2400)))
    assert strong > weak


def test_fide_rating_is_approximated():
    assert outlierness(person(prof("fide", rating=2700))) > 90


def test_an_unknown_platform_with_only_a_rating_scores_zero():
    assert outlierness(person(prof("mystery", rating=2900))) == 0


def test_the_score_never_exceeds_one_hundred():
    p = person(prof("codeforces", rank_pct=99.999), prof("lichess", rating=3200),
               prof("openalex", rank_pct=99.9))
    assert outlierness(p) <= 100


def test_the_score_is_never_negative():
    assert outlierness(person(prof("fide", rating=1000))) >= 0


# -- multi-domain bonus ----------------------------------------------------

def test_two_unrelated_domains_earn_the_bonus():
    p = person(prof("codeforces", rank_pct=99.0), prof("fide", rating=2700))
    assert outlierness(p) > 99.0


def test_the_bonus_is_added_before_the_cap():
    # The bonus is +10 (MULTI_DOMAIN_BONUS), but it can only fire when the
    # person is already >=99th percentile in two domains -- so in practice it
    # always saturates the cap. Documented in docs/normalization.md.
    p = person(prof("codeforces", rank_pct=99.0), prof("fide", rating=2500))
    assert outlierness(p) == 100
    assert MULTI_DOMAIN_BONUS == 10


def test_a_single_elite_domain_does_not_reach_one_hundred():
    assert outlierness(person(prof("codeforces", rank_pct=99.0))) < 100


def test_two_chess_platforms_are_one_domain_not_two():
    # chess blitz + chess rapid != two domains.
    p = person(prof("lichess", rating=2900), prof("fide", rating=2700))
    assert outlierness(p) == outlierness(person(prof("lichess", rating=2900)))


def test_the_bonus_needs_top_one_percent_in_both_domains():
    p = person(prof("codeforces", rank_pct=50.0), prof("fide", rating=2700))
    assert outlierness(p) == outlierness(person(prof("fide", rating=2700)))


def test_the_bonus_cannot_push_past_one_hundred():
    p = person(prof("codeforces", rank_pct=99.99), prof("fide", rating=2800))
    assert outlierness(p) == 100


def test_domains_group_chess_platforms_together():
    assert domains_of({"lichess", "fide"}) == {"chess"}


def test_domains_separate_unrelated_platforms():
    assert domains_of({"codeforces", "fide"}) == {"competitive_programming", "chess"}


def test_every_known_platform_has_a_domain():
    for platform in ("codeforces", "lichess", "fide", "kaggle", "metaculus",
                     "openalex", "ctftime"):
        assert platform in DOMAINS

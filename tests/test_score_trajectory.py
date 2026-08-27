from datetime import datetime, timedelta, timezone

import pytest

from core.score import INACTIVE_DAYS, composite, rank, score_person, trajectory
from core.schema import Person, RawProfile, Scores


def days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def history(points):
    return [{"date": d, "rating": r} for d, r in points]


def prof(platform="codeforces", hist=None, raw=None, **kw):
    return RawProfile(platform=platform, handle="x", rating_history=hist or [],
                      raw=raw or {}, **kw)


def person(*profiles, **kw):
    return Person(id="x", profiles=list(profiles), **kw)


# -- slope -----------------------------------------------------------------

def test_a_rising_player_scores_above_the_midpoint():
    h = history([(days_ago(700), 2400), (days_ago(400), 2500),
                 (days_ago(100), 2600), (days_ago(10), 2700)])
    assert trajectory(person(prof(hist=h))) > 50


def test_a_falling_player_scores_below_the_midpoint():
    h = history([(days_ago(700), 2700), (days_ago(400), 2600),
                 (days_ago(100), 2500), (days_ago(10), 2400)])
    assert trajectory(person(prof(hist=h))) < 50


def test_a_flat_player_scores_near_the_midpoint():
    h = history([(days_ago(700), 2500), (days_ago(400), 2500),
                 (days_ago(100), 2500), (days_ago(10), 2500)])
    assert trajectory(person(prof(hist=h))) == pytest.approx(50, abs=5)


def test_a_steeper_rise_scores_higher():
    slow = history([(days_ago(700), 2400), (days_ago(10), 2450)])
    fast = history([(days_ago(700), 2400), (days_ago(10), 2800)])
    assert trajectory(person(prof(hist=fast))) > trajectory(person(prof(hist=slow)))


def test_only_the_last_twenty_four_months_count():
    ancient = history([(days_ago(3000), 1000), (days_ago(2000), 2800)])
    assert trajectory(person(prof(hist=ancient))) != 100


def test_the_score_stays_within_bounds():
    h = history([(days_ago(700), 1000), (days_ago(10), 3500)])
    assert 0 <= trajectory(person(prof(hist=h))) <= 100


# -- recency ---------------------------------------------------------------

def test_inactivity_decays_the_score():
    recent = history([(days_ago(500), 2400), (days_ago(10), 2700)])
    stale = history([(days_ago(900), 2400), (days_ago(400), 2700)])
    assert trajectory(person(prof(hist=recent))) > trajectory(person(prof(hist=stale)))


def test_activity_inside_the_window_is_not_decayed():
    h = history([(days_ago(600), 2400), (days_ago(INACTIVE_DAYS - 5), 2700)])
    stale = history([(days_ago(600), 2400), (days_ago(INACTIVE_DAYS + 200), 2700)])
    assert trajectory(person(prof(hist=h))) > trajectory(person(prof(hist=stale)))


# -- fallback --------------------------------------------------------------

def test_a_person_with_no_history_gets_the_fallback():
    created = int((datetime.now(timezone.utc) - timedelta(days=400)).timestamp() * 1000)
    p = person(prof("lichess", raw={"created_at": created}))
    assert trajectory(p) > 0


def test_reaching_the_top_fast_scores_higher_than_slowly():
    fast = int((datetime.now(timezone.utc) - timedelta(days=400)).timestamp() * 1000)
    slow = int((datetime.now(timezone.utc) - timedelta(days=6000)).timestamp() * 1000)
    quick = person(prof("lichess", raw={"created_at": fast}))
    veteran = person(prof("lichess", raw={"created_at": slow}))
    assert trajectory(quick) > trajectory(veteran)


def test_no_history_and_no_account_age_scores_the_neutral_midpoint():
    assert trajectory(person(prof())) == 50


# -- #30 composite ---------------------------------------------------------

def test_the_composite_uses_the_specified_weights():
    assert composite(100, 100, 100) == pytest.approx(100)
    assert composite(100, 0, 0) == pytest.approx(45)
    assert composite(0, 100, 0) == pytest.approx(30)
    assert composite(0, 0, 100) == pytest.approx(25)


def test_score_person_produces_a_full_scores_object():
    p = person(prof("codeforces", rank_pct=99.5), birth_year=1990,
               links={"linkedin": "u"}, evidence=["e"])
    s = score_person(p)
    assert isinstance(s, Scores)
    assert s.person_id == "x"
    assert s.composite is not None


def test_an_excluded_person_is_scored_but_marked():
    p = person(prof("lichess", rank_pct=99.5))  # young platform, unknown age
    s = score_person(p)
    assert s.excluded is True and s.exclusion_reasons


def test_flags_are_carried_onto_the_scores():
    p = person(prof("lichess", rank_pct=99.5))
    assert "age_unknown" in score_person(p).flags


def test_ranking_is_deterministic_across_runs():
    people = [person(prof("codeforces", rank_pct=p), birth_year=1990,
                     links={"linkedin": "u"}, evidence=["e"]) for p in (90.0, 95.0)]
    for i, p in enumerate(people):
        p.id = f"p{i}"
    first = [s.person_id for s in rank([score_person(p) for p in people])]
    second = [s.person_id for s in rank([score_person(p) for p in people])]
    assert first == second


def test_ranking_puts_the_higher_composite_first():
    a = person(prof("codeforces", rank_pct=99.9), birth_year=1990,
               links={"linkedin": "u"}, evidence=["e"])
    b = person(prof("codeforces", rank_pct=50.0), birth_year=1990,
               links={"linkedin": "u"}, evidence=["e"])
    a.id, b.id = "a", "b"
    assert [s.person_id for s in rank([score_person(b), score_person(a)])][0] == "a"


def test_excluded_people_rank_below_everyone_included():
    good = person(prof("codeforces", rank_pct=10.0), birth_year=1990,
                  links={"linkedin": "u"}, evidence=["e"])
    bad = person(prof("codeforces", rank_pct=99.9))  # no surface, single source
    good.id, bad.id = "good", "bad"
    ranked = rank([score_person(bad), score_person(good)])
    assert ranked[0].person_id == "good"


def test_ties_break_on_person_id_for_stability():
    people = []
    for pid in ("b", "a"):
        p = person(prof("codeforces", rank_pct=90.0), birth_year=1990,
                   links={"linkedin": "u"}, evidence=["e"])
        p.id = pid
        people.append(p)
    assert [s.person_id for s in rank([score_person(p) for p in people])] == ["a", "b"]

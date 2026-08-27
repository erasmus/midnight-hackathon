import pytest
from core.schema import RawProfile, Person, Scores


def make_raw():
    return RawProfile(
        platform="codeforces",
        handle="tourist",
        display_name="Gennady Korotkevich",
        url="https://codeforces.com/profile/tourist",
        rating=3800,
        rank_pct=99.99,
        rating_history=[{"date": "2020-01-01", "rating": 3500}],
        profile_links=["https://github.com/tourist"],
        country="BY",
        birth_year=1994,
        raw={"anything": 1},
        fetched_at="2026-08-28T00:00:00Z",
    )


def test_raw_profile_round_trips_through_dict():
    raw = make_raw()
    assert RawProfile.from_dict(raw.to_dict()) == raw


def test_person_round_trips_through_dict():
    person = Person(
        id="codeforces:tourist",
        display_name="Gennady Korotkevich",
        birth_year=1994,
        country="BY",
        profiles=[make_raw()],
        links={"github": "https://github.com/tourist"},
        evidence=["handle reuse: codeforces:tourist -> github:tourist"],
    )
    assert Person.from_dict(person.to_dict()) == person


def test_person_with_resolved_link_requires_evidence():
    with pytest.raises(ValueError):
        Person(
            id="codeforces:tourist",
            display_name="Gennady Korotkevich",
            profiles=[make_raw()],
            links={"github": "https://github.com/tourist"},
            evidence=[],
        )


def test_person_without_resolved_links_needs_no_evidence():
    person = Person(id="codeforces:tourist", display_name="tourist", profiles=[make_raw()])
    assert person.evidence == []


def test_scores_round_trips_and_supports_required_flags():
    scores = Scores(
        person_id="codeforces:tourist",
        outlierness=90.0,
        trajectory=70.0,
        addressability=40.0,
        composite=72.5,
        flags=["age_unknown", "single_source", "already_founder"],
    )
    assert Scores.from_dict(scores.to_dict()) == scores


def test_scores_rejects_unknown_flag():
    with pytest.raises(ValueError):
        Scores(person_id="x", flags=["not_a_real_flag"])

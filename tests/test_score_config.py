import pytest

from core.score import (
    DEFAULT_CONFIG, ScoringConfig, composite, hard_filter, score, score_person,
)
from core.schema import Person, RawProfile


_DEFAULT_LINKS = object()


def person(pid="x", platforms=("codeforces",), birth_year=1990, links=_DEFAULT_LINKS, **kw):
    profiles = [RawProfile(platform=p, handle="h", rank_pct=99.0) for p in platforms]
    # `links={}` must mean "no links", not "use the default".
    links = {"linkedin": "u"} if links is _DEFAULT_LINKS else links
    return Person(id=pid, display_name="A B", birth_year=birth_year, profiles=profiles,
                  links=links, evidence=["e"] if links else [], **kw)


# -- defaults preserve existing behaviour ----------------------------------

def test_the_default_config_matches_the_documented_weights():
    assert DEFAULT_CONFIG.weights == {"outlierness": 0.45, "trajectory": 0.30,
                                      "addressability": 0.25}


def test_the_default_age_floor_is_eighteen():
    assert DEFAULT_CONFIG.min_age == 18


def test_the_default_is_strict_about_young_platforms():
    assert DEFAULT_CONFIG.strict_young_platform is True


def test_composite_without_a_config_uses_the_defaults():
    assert composite(100, 0, 0) == pytest.approx(45)


def test_score_person_without_a_config_is_unchanged():
    assert score_person(person()).composite is not None


# -- weights ---------------------------------------------------------------

def test_custom_weights_change_the_composite():
    config = ScoringConfig(weights={"outlierness": 1.0, "trajectory": 0.0,
                                    "addressability": 0.0})
    assert composite(100, 0, 0, config) == pytest.approx(100)


def test_weights_are_applied_to_each_dimension():
    config = ScoringConfig(weights={"outlierness": 0.0, "trajectory": 1.0,
                                    "addressability": 0.0})
    assert composite(0, 80, 0, config) == pytest.approx(80)


def test_score_person_respects_custom_weights():
    p = person()
    heavy_addr = ScoringConfig(weights={"outlierness": 0.0, "trajectory": 0.0,
                                        "addressability": 1.0})
    assert score_person(p, heavy_addr).composite == pytest.approx(
        score_person(p).addressability)


# -- age floor -------------------------------------------------------------

def test_a_lower_age_floor_admits_a_younger_person():
    young = person(birth_year=2010)
    assert hard_filter(young).excluded is True
    assert hard_filter(young, ScoringConfig(min_age=10)).excluded is False


def test_a_higher_age_floor_excludes_an_older_person():
    p = person(birth_year=2004)
    assert hard_filter(p).excluded is False
    assert hard_filter(p, ScoringConfig(min_age=30)).excluded is True


def test_the_age_reason_names_the_configured_floor():
    result = hard_filter(person(birth_year=2004), ScoringConfig(min_age=30))
    assert "30" in " ".join(result.reasons)


# -- young-platform strictness ---------------------------------------------

def test_strict_mode_excludes_unknown_age_on_a_young_platform():
    p = person(birth_year=None, platforms=("lichess",))
    assert hard_filter(p).excluded is True


def test_lenient_mode_admits_unknown_age_but_still_flags_it():
    p = person(birth_year=None, platforms=("lichess",))
    result = hard_filter(p, ScoringConfig(strict_young_platform=False))
    assert result.excluded is False
    assert "age_unknown" in result.flags


def test_lenient_mode_does_not_disable_the_hard_age_floor():
    # Being lenient about *unknown* age must never admit a known minor.
    p = person(birth_year=2015, platforms=("lichess",))
    assert hard_filter(p, ScoringConfig(strict_young_platform=False)).excluded is True


# -- relevance gate --------------------------------------------------------

def test_the_relevance_gate_can_be_disabled():
    p = person(links={}, platforms=("codeforces",))
    assert hard_filter(p).excluded is True
    assert hard_filter(p, ScoringConfig(require_surface=False)).excluded is False


# -- batch -----------------------------------------------------------------

def test_score_passes_the_config_to_every_person():
    people = [person(pid="a", birth_year=2010), person(pid="b", birth_year=2010)]
    results = score(people, ScoringConfig(min_age=10))
    assert all(not s.excluded for s in results)


def test_the_config_is_immutable():
    with pytest.raises(Exception):
        DEFAULT_CONFIG.min_age = 21

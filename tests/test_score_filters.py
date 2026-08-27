import pytest

from core.score import (
    CURRENT_YEAR, MIN_AGE, addressability, hard_filter, has_professional_surface,
)
from core.schema import Person, RawProfile


def person(pid="codeforces:x", links=None, birth_year=None, platforms=("codeforces",),
           enrichment=None, evidence=None):
    profiles = [RawProfile(platform=p, handle="x") for p in platforms]
    return Person(id=pid, display_name="X Y", birth_year=birth_year, profiles=profiles,
                  links=links or {}, evidence=evidence or (["e"] if links else []),
                  enrichment=enrichment or {})


ACTIVE = {"github_activity": {"active": True}}


# -- #29 addressability ----------------------------------------------------

def test_github_with_verified_activity_scores_forty():
    assert addressability(person(links={"github": "u"}, enrichment=ACTIVE)) == 40


def test_a_github_account_without_verified_activity_scores_nothing():
    # "GitHub with real activity", not "has a GitHub account".
    assert addressability(person(links={"github": "u"})) == 0


def test_github_explicitly_inactive_scores_nothing():
    inactive = {"github_activity": {"active": False}}
    assert addressability(person(links={"github": "u"}, enrichment=inactive)) == 0


def test_linkedin_self_link_scores_twenty_five():
    assert addressability(person(links={"linkedin": "u"})) == 25


def test_personal_site_scores_twenty():
    assert addressability(person(links={"personal_site": "u"})) == 20


def test_papers_score_fifteen():
    assert addressability(person(links={"papers": "u"})) == 15


def test_surfaces_add_up():
    p = person(links={"github": "g", "linkedin": "l", "personal_site": "s"},
               enrichment=ACTIVE)
    assert addressability(p) == 85


def test_the_score_is_capped_at_one_hundred():
    p = person(links={"github": "g", "linkedin": "l", "personal_site": "s",
                      "papers": "p"}, enrichment=ACTIVE)
    assert addressability(p) == 100


def test_no_surface_scores_zero():
    assert addressability(person()) == 0


def test_an_unrelated_link_kind_does_not_score():
    assert addressability(person(links={"twitter": "t"})) == 0


# -- professional surface --------------------------------------------------

def test_a_github_link_is_a_professional_surface_even_unverified():
    assert has_professional_surface(person(links={"github": "u"})) is True


def test_twitter_alone_is_not_a_professional_surface():
    assert has_professional_surface(person(links={"twitter": "t"})) is False


def test_no_links_is_no_surface():
    assert has_professional_surface(person()) is False


# -- #26 hard filters ------------------------------------------------------

def test_a_minor_is_excluded():
    result = hard_filter(person(birth_year=CURRENT_YEAR - 10,
                                links={"linkedin": "u"}))
    assert result.excluded is True


def test_the_exclusion_reason_names_the_age():
    result = hard_filter(person(birth_year=CURRENT_YEAR - 10, links={"linkedin": "u"}))
    assert any("18" in r or "age" in r.lower() for r in result.reasons)


def test_an_adult_is_not_excluded_on_age():
    result = hard_filter(person(birth_year=CURRENT_YEAR - 30, links={"linkedin": "u"}))
    assert result.excluded is False


def test_exactly_eighteen_is_allowed():
    result = hard_filter(person(birth_year=CURRENT_YEAR - MIN_AGE,
                                links={"linkedin": "u"}))
    assert result.excluded is False


def test_an_unknown_age_is_flagged():
    result = hard_filter(person(links={"linkedin": "u"}))
    assert "age_unknown" in result.flags


def test_an_unknown_age_on_a_young_skewing_platform_is_excluded():
    # Chess and competitive programming leaderboards are full of minors.
    result = hard_filter(person(links={"linkedin": "u"}, platforms=("lichess",)))
    assert result.excluded is True


def test_an_unknown_age_with_adulthood_evidence_survives():
    p = person(links={"linkedin": "u"}, platforms=("lichess",),
               enrichment={"adulthood_evidence": "MSc graduation 2019"})
    assert hard_filter(p).excluded is False


def test_an_unknown_age_on_a_neutral_platform_is_not_excluded():
    result = hard_filter(person(links={"linkedin": "u"}, platforms=("openalex",)))
    assert result.excluded is False


def test_a_known_founder_is_excluded():
    p = person(birth_year=1990, links={"linkedin": "u"},
               enrichment={"already_founder": {"company": "Acme"}})
    result = hard_filter(p)
    assert result.excluded is True
    assert "already_founder" in result.flags


def test_a_single_source_person_with_no_surface_is_excluded():
    result = hard_filter(person(birth_year=1990))
    assert result.excluded is True
    assert any("surface" in r.lower() for r in result.reasons)


def test_a_single_source_person_with_a_surface_survives():
    result = hard_filter(person(birth_year=1990, links={"linkedin": "u"}))
    assert result.excluded is False


def test_a_multi_source_person_with_no_surface_survives():
    p = person(birth_year=1990, platforms=("codeforces", "lichess"))
    assert hard_filter(p).excluded is False


def test_single_source_is_flagged_even_when_not_excluded():
    result = hard_filter(person(birth_year=1990, links={"linkedin": "u"}))
    assert "single_source" in result.flags


def test_multi_source_is_not_flagged_single_source():
    p = person(birth_year=1990, links={"linkedin": "u"},
               platforms=("codeforces", "lichess"))
    assert "single_source" not in hard_filter(p).flags


def test_every_exclusion_carries_at_least_one_reason():
    p = person(birth_year=CURRENT_YEAR - 5)
    result = hard_filter(p)
    assert result.excluded and result.reasons


def test_several_failures_are_all_reported():
    p = person(birth_year=CURRENT_YEAR - 5)  # minor AND no surface AND single source
    assert len(hard_filter(p).reasons) >= 2

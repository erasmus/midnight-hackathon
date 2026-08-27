import pytest

from core.resolve import identify_platform_profile, resolve
from core.schema import Person, RawProfile


def cf(handle="tourist", name="Gennady Korotkevich", links=None, **kw):
    return RawProfile(platform="codeforces", handle=handle, display_name=name,
                      profile_links=links or [], **kw)


def li(handle="Alice", name="Alice Adams", links=None, **kw):
    return RawProfile(platform="lichess", handle=handle, display_name=name,
                      profile_links=links or [], **kw)


class NoGitHub:
    def get_json(self, url):
        raise RuntimeError("404")


class FakeGitHub:
    def __init__(self, users):
        self.users = users
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        handle = url.rstrip("/").split("/")[-1]
        if handle not in self.users:
            raise RuntimeError("404")
        return self.users[handle]


def solo(profiles, **kw):
    kw.setdefault("github_client", NoGitHub())
    return resolve(profiles, **kw)


def by_id(persons):
    return {p.id: p for p in persons}


# -- platform URL recognition ----------------------------------------------

def test_a_codeforces_profile_url_is_recognised():
    assert identify_platform_profile("https://codeforces.com/profile/tourist") == (
        "codeforces", "tourist")


def test_a_lichess_profile_url_is_recognised():
    assert identify_platform_profile("https://lichess.org/@/Alice") == ("lichess", "Alice")


def test_an_unrelated_url_is_not_a_platform_profile():
    assert identify_platform_profile("https://github.com/alice") is None


# -- no merge by default ---------------------------------------------------

def test_each_profile_becomes_its_own_person_without_a_mechanism():
    persons = solo([cf(), li()])
    assert len(persons) == 2


def test_a_shared_display_name_alone_never_merges():
    # Name collision is not a sanctioned mechanism. This is the whole point.
    persons = solo([cf(handle="a", name="John Smith"), li(handle="b", name="John Smith")])
    assert len(persons) == 2


def test_a_shared_handle_alone_never_merges():
    persons = solo([cf(handle="magnus"), li(handle="magnus")])
    assert len(persons) == 2


def test_person_ids_are_deterministic_across_runs():
    profiles = [cf(), li()]
    assert [p.id for p in solo(profiles)] == [p.id for p in solo(profiles)]


def test_person_id_does_not_depend_on_input_order():
    a = solo([cf(links=["https://lichess.org/@/Alice"]), li()])
    b = solo([li(), cf(links=["https://lichess.org/@/Alice"])])
    assert [p.id for p in a] == [p.id for p in b]


# -- mechanism 1: self-link ------------------------------------------------

def test_a_self_link_to_another_platform_merges_the_profiles():
    persons = solo([cf(links=["https://lichess.org/@/Alice"]), li()])
    assert len(persons) == 1
    assert {p.platform for p in persons[0].profiles} == {"codeforces", "lichess"}


def test_a_self_link_merge_is_explained_in_the_evidence():
    (person,) = solo([cf(links=["https://lichess.org/@/Alice"]), li()])
    assert any("lichess" in e and "codeforces" in e for e in person.evidence)


def test_a_self_link_to_a_platform_profile_we_did_not_fetch_does_not_merge():
    persons = solo([cf(links=["https://lichess.org/@/NotFetched"]), li()])
    assert len(persons) == 2


def test_an_off_platform_self_link_is_stored_on_the_person():
    (person,) = solo([cf(links=["https://github.com/tourist"])])
    assert person.links["github"] == "https://github.com/tourist"


def test_every_stored_link_has_evidence():
    (person,) = solo([cf(links=["https://github.com/tourist", "https://tourist.dev"])])
    assert person.links and person.evidence
    assert len(person.evidence) >= len(person.links)


def test_a_linkedin_link_is_stored_but_never_fetched():
    (person,) = solo([cf(links=["https://linkedin.com/in/gennady"])])
    assert person.links["linkedin"] == "https://linkedin.com/in/gennady"


def test_a_personal_site_is_kept_as_a_candidate():
    (person,) = solo([cf(links=["https://tourist.dev"])])
    assert person.links["personal_site"] == "https://tourist.dev"


# -- mechanism 2: corroborated handle reuse --------------------------------

def test_a_corroborated_github_match_stores_the_link():
    gh = FakeGitHub({"tourist": {"login": "tourist", "name": "Gennady Korotkevich",
                                 "html_url": "https://github.com/tourist"}})
    (person,) = resolve([cf()], github_client=gh)
    assert person.links["github"] == "https://github.com/tourist"


def test_an_uncorroborated_github_collision_is_never_surfaced():
    gh = FakeGitHub({"tourist": {"login": "tourist", "html_url": "https://github.com/tourist"}})
    (person,) = resolve([cf()], github_client=gh)
    assert "github" not in person.links


def test_an_uncorroborated_collision_is_recorded_as_a_weak_match():
    gh = FakeGitHub({"tourist": {"login": "tourist", "html_url": "https://github.com/tourist"}})
    (person,) = resolve([cf()], github_client=gh)
    assert person.weak_matches and "no corroborating" in person.weak_matches[0]


def test_a_weak_match_does_not_appear_in_evidence():
    gh = FakeGitHub({"tourist": {"login": "tourist", "html_url": "https://github.com/tourist"}})
    (person,) = resolve([cf()], github_client=gh)
    assert not any("weak" in e.lower() for e in person.evidence)


def test_two_profiles_corroborated_to_the_same_github_account_merge():
    gh = FakeGitHub({
        "tourist": {"login": "tourist", "name": "Gennady Korotkevich",
                    "html_url": "https://github.com/tourist"},
    })
    persons = resolve([cf(handle="tourist"), li(handle="tourist", name="Gennady Korotkevich")],
                      github_client=gh)
    assert len(persons) == 1


def test_two_profiles_weakly_colliding_on_the_same_github_account_do_not_merge():
    gh = FakeGitHub({"tourist": {"login": "tourist", "html_url": "https://github.com/tourist"}})
    persons = resolve([cf(handle="tourist"), li(handle="tourist")], github_client=gh)
    assert len(persons) == 2


def test_github_lookups_are_capped_to_the_top_slice():
    gh = FakeGitHub({})
    resolve([cf(handle="a"), cf(handle="b"), cf(handle="c")], github_client=gh, github_for=2)
    assert len(gh.calls) == 2


def test_github_matching_is_skipped_entirely_when_disabled():
    gh = FakeGitHub({})
    resolve([cf()], github_client=gh, github_for=0)
    assert gh.calls == []


# -- person construction ---------------------------------------------------

def test_a_merged_person_keeps_every_profile():
    (person,) = solo([cf(links=["https://lichess.org/@/Alice"]), li()])
    assert len(person.profiles) == 2


def test_a_merged_person_prefers_a_published_real_name():
    (person,) = solo([cf(handle="tourist", name="tourist",
                         links=["https://lichess.org/@/Alice"]), li(name="Alice Adams")])
    assert person.display_name == "Alice Adams"


def test_country_is_taken_from_whichever_profile_declares_one():
    (person,) = solo([cf(links=["https://lichess.org/@/Alice"]), li(country="DK")])
    assert person.country == "DK"


def test_birth_year_is_taken_from_whichever_profile_declares_one():
    (person,) = solo([cf(links=["https://lichess.org/@/Alice"]), li(birth_year=1994)])
    assert person.birth_year == 1994


def test_resolve_returns_person_objects():
    assert all(isinstance(p, Person) for p in solo([cf(), li()]))


def test_an_empty_input_yields_no_people():
    assert solo([]) == []


def test_resolve_never_raises_on_a_person_with_links_but_no_evidence():
    # Person enforces this at construction; resolve must always satisfy it.
    persons = solo([cf(links=["https://github.com/tourist", "https://x.com/tourist"])])
    assert persons[0].evidence

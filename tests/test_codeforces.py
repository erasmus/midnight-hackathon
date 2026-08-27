import json

import pytest

from adapters import codeforces
from core.schema import RawProfile


class FakeClient:
    """Stands in for core.http.HttpClient, serving canned URL -> payload."""

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        for fragment, payload in self.payloads.items():
            if fragment in url:
                return payload
        raise AssertionError(f"unexpected URL {url}")


def user(handle, rating, **extra):
    return {"handle": handle, "rating": rating, "maxRating": rating, **extra}


def rated_list(users):
    return {"status": "OK", "result": users}


def history(entries):
    return {"status": "OK", "result": entries}


# Filler population sits well below the 2400 floor, so only the two named
# users survive the filter.
POPULATION = [user(f"u{i}", 800 + (i % 1000)) for i in range(2000)] + [
    user("tourist", 3800, country="Belarus", organization="ITMO",
         firstName="Gennady", lastName="Korotkevich"),
    user("benq", 2500, country="United States"),
]


def client_for(users, histories=None):
    payloads = {"user.ratedList": rated_list(users)}
    payloads.update(histories or {})
    return FakeClient(payloads)


def test_returns_raw_profiles_for_the_codeforces_platform():
    profiles = codeforces.fetch_top(10, client=client_for(POPULATION), history_for=0)
    assert profiles and all(isinstance(p, RawProfile) for p in profiles)
    assert {p.platform for p in profiles} == {"codeforces"}


def test_only_users_at_or_above_the_rating_floor_are_returned():
    profiles = codeforces.fetch_top(500, client=client_for(POPULATION), history_for=0)
    assert {p.handle for p in profiles} == {"tourist", "benq"}


def test_results_are_ordered_by_rating_descending():
    profiles = codeforces.fetch_top(500, client=client_for(POPULATION), history_for=0)
    assert [p.handle for p in profiles] == ["tourist", "benq"]


def test_requested_count_caps_the_result():
    profiles = codeforces.fetch_top(1, client=client_for(POPULATION), history_for=0)
    assert [p.handle for p in profiles] == ["tourist"]


def test_never_returns_more_than_the_platform_cap():
    everyone = [user(f"strong{i}", 2400 + i) for i in range(600)]
    profiles = codeforces.fetch_top(10_000, client=client_for(everyone), history_for=0)
    assert len(profiles) == codeforces.MAX_PROFILES


def test_percentile_is_computed_against_the_full_rated_population():
    profiles = codeforces.fetch_top(500, client=client_for(POPULATION), history_for=0)
    top = {p.handle: p for p in profiles}
    # tourist is the single highest of 2002 rated users.
    assert top["tourist"].rank_pct == pytest.approx(100 * 2001 / 2002, abs=0.01)


def test_percentile_uses_the_whole_population_not_just_the_returned_slice():
    profiles = codeforces.fetch_top(1, client=client_for(POPULATION), history_for=0)
    assert profiles[0].rank_pct > 99


def test_the_rated_list_is_fetched_once_for_the_whole_population():
    c = client_for(POPULATION)
    codeforces.fetch_top(500, client=c, history_for=0)
    assert sum("ratedList" in url for url in c.calls) == 1


def test_display_name_is_built_from_first_and_last_name():
    profiles = codeforces.fetch_top(1, client=client_for(POPULATION), history_for=0)
    assert profiles[0].display_name == "Gennady Korotkevich"


def test_handle_is_used_as_display_name_when_no_real_name_is_published():
    profiles = codeforces.fetch_top(500, client=client_for(POPULATION), history_for=0)
    benq = next(p for p in profiles if p.handle == "benq")
    assert benq.display_name == "benq"


def test_country_and_organization_are_captured():
    profiles = codeforces.fetch_top(1, client=client_for(POPULATION), history_for=0)
    assert profiles[0].country == "Belarus"
    assert profiles[0].raw["organization"] == "ITMO"


def test_profile_url_points_at_the_public_profile():
    profiles = codeforces.fetch_top(1, client=client_for(POPULATION), history_for=0)
    assert profiles[0].url == "https://codeforces.com/profile/tourist"


def test_rating_history_is_populated_with_dated_contest_results():
    histories = {
        "user.rating": history(
            [{"contestId": 1, "contestName": "CF Round 1",
              "ratingUpdateTimeSeconds": 1577836800, "newRating": 3800, "rank": 1}]
        )
    }
    profiles = codeforces.fetch_top(1, client=client_for(POPULATION, histories), history_for=1)
    assert profiles[0].rating_history == [
        {"date": "2020-01-01", "rating": 3800, "contest": "CF Round 1", "rank": 1}
    ]


def test_history_is_only_fetched_for_the_top_slice():
    histories = {"user.rating": history([])}
    c = client_for(POPULATION, histories)
    codeforces.fetch_top(500, client=c, history_for=1)
    assert sum("user.rating?" in url for url in c.calls) == 1


def test_a_failed_history_fetch_does_not_lose_the_profile():
    class Flaky(FakeClient):
        def get_json(self, url):
            if "user.rating?" in url:
                raise RuntimeError("500")
            return super().get_json(url)

    c = Flaky({"user.ratedList": rated_list(POPULATION)})
    profiles = codeforces.fetch_top(1, client=c, history_for=1)
    assert profiles[0].handle == "tourist"
    assert profiles[0].rating_history == []


def test_an_api_level_failure_is_raised():
    c = FakeClient({"user.ratedList": {"status": "FAILED", "comment": "nope"}})
    with pytest.raises(RuntimeError):
        codeforces.fetch_top(10, client=c, history_for=0)


def test_fetched_at_is_stamped_on_every_profile():
    profiles = codeforces.fetch_top(500, client=client_for(POPULATION), history_for=0)
    assert all(p.fetched_at for p in profiles)


def test_adapter_exposes_the_pipeline_interface():
    assert callable(codeforces.fetch_top)
    assert codeforces.name == "codeforces"

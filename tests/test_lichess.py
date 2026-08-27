import pytest

from adapters import lichess
from core.schema import RawProfile


class FakeClient:
    def __init__(self, tops=None, users=None, histories=None):
        self.tops = tops or {}
        self.users = users or []
        self.histories = histories or {}
        self.calls = []
        self.posts = []

    def get_json(self, url):
        self.calls.append(url)
        for control, payload in self.tops.items():
            if f"/top/200/{control}" in url:
                return payload
        if "/rating-history" in url:
            handle = url.split("/api/user/")[1].split("/")[0]
            if handle in self.histories:
                return self.histories[handle]
            raise AssertionError(f"no history stubbed for {handle}")
        raise AssertionError(f"unexpected GET {url}")

    def post_json(self, url, data=None, accept=None):
        self.calls.append(url)
        self.posts.append(data)
        wanted = set(data.split(","))
        return [u for u in self.users if u["username"] in wanted]


def top(users):
    return {"users": users}


def top_user(username, rating, control="blitz", **extra):
    return {
        "id": username.lower(),
        "username": username,
        "perfs": {control: {"rating": rating, "progress": 0}},
        **extra,
    }


def full_user(username, **profile):
    return {
        "id": username.lower(),
        "username": username,
        "title": profile.pop("title", None),
        "profile": profile,
        "perfs": {"blitz": {"rating": 2900, "games": 5000}},
        "createdAt": 1400000000000,
    }


def client_for(tops, users=None, histories=None):
    return FakeClient(tops=tops, users=users or [], histories=histories or {})


BASIC_TOPS = {
    "blitz": top([top_user("Alice", 2900), top_user("Bob", 2850)]),
    "rapid": top([top_user("Alice", 2800, "rapid"), top_user("Carol", 2790, "rapid")]),
    "classical": top([top_user("Bob", 2700, "classical")]),
}
BASIC_USERS = [full_user("Alice"), full_user("Bob"), full_user("Carol")]


def fetch(client, n=500, **kw):
    kw.setdefault("history_for", 0)
    return lichess.fetch_top(n, client=client, **kw)


def test_returns_raw_profiles_for_the_lichess_platform():
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS))
    assert profiles and all(isinstance(p, RawProfile) for p in profiles)
    assert {p.platform for p in profiles} == {"lichess"}


def test_players_are_deduped_across_time_controls():
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS))
    assert sorted(p.handle for p in profiles) == ["Alice", "Bob", "Carol"]


def test_every_time_control_leaderboard_is_fetched():
    c = client_for(BASIC_TOPS, BASIC_USERS)
    fetch(c)
    for control in lichess.TIME_CONTROLS:
        assert any(f"/top/200/{control}" in url for url in c.calls)


def test_rating_is_the_players_best_across_time_controls():
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, BASIC_USERS))}
    assert profiles["Alice"].rating == 2900
    assert profiles["Bob"].rating == 2850


def test_per_control_ratings_are_kept():
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, BASIC_USERS))}
    assert profiles["Alice"].raw["ratings"] == {"blitz": 2900, "rapid": 2800}


def test_results_are_ordered_by_best_rating_descending():
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS))
    assert [p.handle for p in profiles] == ["Alice", "Bob", "Carol"]


def test_requested_count_caps_the_result():
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS), n=2)
    assert [p.handle for p in profiles] == ["Alice", "Bob"]


def test_never_returns_more_than_the_platform_cap():
    many = [top_user(f"P{i}", 3000 - i) for i in range(600)]
    users = [full_user(f"P{i}") for i in range(600)]
    profiles = fetch(client_for({"blitz": top(many)}, users), n=10_000)
    assert len(profiles) == lichess.MAX_PROFILES


def test_details_are_fetched_in_bulk_not_one_request_per_player():
    c = client_for(BASIC_TOPS, BASIC_USERS)
    fetch(c)
    assert len(c.posts) == 1


def test_bulk_requests_are_batched_within_the_api_limit():
    many = [top_user(f"P{i}", 3000 - i) for i in range(500)]
    users = [full_user(f"P{i}") for i in range(500)]
    c = client_for({"blitz": top(many)}, users)
    fetch(c)
    assert all(len(body.split(",")) <= lichess.BULK_BATCH for body in c.posts)
    assert len(c.posts) == 2


def test_title_is_stored_as_a_join_key():
    users = [full_user("Alice", title="GM"), full_user("Bob"), full_user("Carol")]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].raw["title"] == "GM"


def test_declared_fide_rating_is_stored_as_a_join_key():
    users = [full_user("Alice", fideRating=2700), full_user("Bob"), full_user("Carol")]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].raw["fide_rating"] == 2700


def test_bio_links_land_in_profile_links():
    users = [
        full_user("Alice", links="https://github.com/alice\nhttps://alice.dev"),
        full_user("Bob"),
        full_user("Carol"),
    ]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].profile_links == [
        "https://github.com/alice",
        "https://alice.dev",
    ]


def test_urls_written_into_the_bio_are_also_captured():
    users = [
        full_user("Alice", bio="my code: https://github.com/alice come say hi"),
        full_user("Bob"),
        full_user("Carol"),
    ]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert "https://github.com/alice" in profiles["Alice"].profile_links


def test_a_link_is_not_recorded_twice():
    users = [
        full_user("Alice", bio="https://github.com/alice", links="https://github.com/alice"),
        full_user("Bob"),
        full_user("Carol"),
    ]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].profile_links == ["https://github.com/alice"]


def test_a_player_with_no_bio_has_no_links():
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, BASIC_USERS))}
    assert profiles["Alice"].profile_links == []


def test_real_name_is_used_as_display_name_when_published():
    users = [
        full_user("Alice", firstName="Alice", lastName="Adams"),
        full_user("Bob"), full_user("Carol"),
    ]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].display_name == "Alice Adams"


def test_username_is_the_display_name_when_no_real_name_is_published():
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, BASIC_USERS))}
    assert profiles["Alice"].display_name == "Alice"


def test_declared_country_is_captured():
    users = [full_user("Alice", flag="DK"), full_user("Bob"), full_user("Carol")]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].country == "DK"


def test_profile_url_points_at_the_public_profile():
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, BASIC_USERS))}
    assert profiles["Alice"].url == "https://lichess.org/@/Alice"


def test_rating_history_is_populated_with_dated_points():
    histories = {"Alice": [{"name": "Blitz", "points": [[2020, 0, 15, 2800]]}]}
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS, histories), n=1, history_for=1)
    assert profiles[0].rating_history == [
        {"date": "2020-01-15", "rating": 2800, "control": "Blitz"}
    ]


def test_history_months_are_converted_from_the_zero_indexed_api():
    histories = {"Alice": [{"name": "Blitz", "points": [[2021, 11, 1, 2900]]}]}
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS, histories), n=1, history_for=1)
    assert profiles[0].rating_history[0]["date"] == "2021-12-01"


def test_history_is_only_fetched_for_the_top_slice():
    histories = {"Alice": []}
    c = client_for(BASIC_TOPS, BASIC_USERS, histories)
    fetch(c, history_for=1)
    assert sum("/rating-history" in url for url in c.calls) == 1


def test_empty_history_series_are_dropped():
    histories = {"Alice": [{"name": "Bullet", "points": []}]}
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS, histories), n=1, history_for=1)
    assert profiles[0].rating_history == []


def test_a_failed_history_fetch_does_not_lose_the_profile():
    class Flaky(FakeClient):
        def get_json(self, url):
            if "/rating-history" in url:
                raise RuntimeError("503")
            return super().get_json(url)

    c = Flaky(tops=BASIC_TOPS, users=BASIC_USERS)
    profiles = fetch(c, n=1, history_for=1)
    assert profiles[0].handle == "Alice"
    assert profiles[0].rating_history == []


def test_a_failed_leaderboard_does_not_lose_the_other_time_controls():
    class Flaky(FakeClient):
        def get_json(self, url):
            if "/top/200/rapid" in url:
                raise RuntimeError("503")
            return super().get_json(url)

    c = Flaky(tops=BASIC_TOPS, users=BASIC_USERS)
    profiles = fetch(c)
    assert sorted(p.handle for p in profiles) == ["Alice", "Bob"]


def test_a_player_missing_from_the_bulk_response_is_still_returned():
    users = [full_user("Alice"), full_user("Bob")]  # Carol absent
    profiles = fetch(client_for(BASIC_TOPS, users))
    assert "Carol" in {p.handle for p in profiles}


def test_percentile_is_left_unset_because_the_population_is_unknown():
    # Unlike Codeforces, Lichess exposes only the top 200 -- there is no
    # denominator, so claiming a percentile here would be a fabrication.
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS))
    assert all(p.rank_pct is None for p in profiles)


def test_leaderboard_rank_is_recorded_per_time_control():
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, BASIC_USERS))}
    assert profiles["Bob"].raw["top_rank"] == {"blitz": 2, "classical": 1}


def test_fetched_at_is_stamped_on_every_profile():
    profiles = fetch(client_for(BASIC_TOPS, BASIC_USERS))
    assert all(p.fetched_at for p in profiles)


def test_adapter_exposes_the_pipeline_interface():
    assert callable(lichess.fetch_top)
    assert lichess.name == "lichess"


def test_link_provenance_records_the_field_each_url_came_from():
    users = [
        full_user("Alice", links="https://github.com/alice", bio="also https://alice.dev"),
        full_user("Bob"), full_user("Carol"),
    ]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].raw["link_sources"] == {
        "https://github.com/alice": "links field",
        "https://alice.dev": "bio",
    }


def test_a_url_in_both_bio_and_links_is_credited_to_the_links_field():
    users = [
        full_user("Alice", links="https://github.com/alice", bio="https://github.com/alice"),
        full_user("Bob"), full_user("Carol"),
    ]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].raw["link_sources"] == {"https://github.com/alice": "links field"}


def test_the_published_real_name_is_used_as_the_display_name():
    # Lichess publishes this as profile.realName -- not firstName/lastName.
    users = [full_user("Alice", realName="Alice Adams"), full_user("Bob"), full_user("Carol")]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].display_name == "Alice Adams"


def test_real_name_wins_over_split_name_fields():
    users = [
        full_user("Alice", realName="Alice Adams", firstName="A", lastName="Adams"),
        full_user("Bob"), full_user("Carol"),
    ]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].display_name == "Alice Adams"


def test_a_blank_real_name_falls_back_to_the_username():
    users = [full_user("Alice", realName="   "), full_user("Bob"), full_user("Carol")]
    profiles = {p.handle: p for p in fetch(client_for(BASIC_TOPS, users))}
    assert profiles["Alice"].display_name == "Alice"

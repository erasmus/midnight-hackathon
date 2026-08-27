from adapters import metaculus
from core.schema import RawProfile


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        for fragment, payload in self.payloads.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected URL {url}")


def test_parses_global_leaderboard_entries():
    client = FakeClient(
        {
            "leaderboards/global": {
                "entries": [
                    {"rank": 1, "score": 1840.2, "user": {"id": 9, "username": "jpark"}},
                    {"rank": 2, "score": 1200, "user": {"id": 8, "username": "hnasser"}},
                ]
            },
            "/api2/users/9/": {
                "id": 9,
                "username": "jpark",
                "name": "Jun Park",
                "bio": "essays at https://parkjun.kr also https://github.com/junpark",
            },
            "/api2/users/8/": {"id": 8, "username": "hnasser", "bio": ""},
        }
    )
    profiles = metaculus.fetch_top(10, client=client, token="", detail_for=10)
    assert [p.handle for p in profiles] == ["jpark", "hnasser"]
    assert profiles[0].display_name == "Jun Park"
    assert profiles[0].rating == 1840.2
    assert "https://github.com/junpark" in profiles[0].profile_links
    assert profiles[0].platform == "metaculus"
    assert isinstance(profiles[0], RawProfile)


def test_falls_back_to_api2_rankings_when_global_board_fails():
    client = FakeClient(
        {
            "leaderboards/global": RuntimeError("403"),
            "api2/rankings": {
                "results": [{"id": 3, "username": "alice", "score": 99, "rank": 1}]
            },
            "/api2/users/3/": RuntimeError("404"),
            "/api/users/3/": {"id": 3, "username": "alice", "bio": "hi"},
        }
    )
    profiles = metaculus.fetch_top(10, client=client, token="", detail_for=1)
    assert profiles[0].handle == "alice"
    assert any("api2/rankings" in u for u in client.calls)


def test_unrecognised_json_returns_empty_instead_of_raising():
    client = FakeClient({"leaderboards/global": {"nope": True}, "api2/rankings": [1, 2, 3]})
    assert metaculus.fetch_top(10, client=client, token="") == []


def test_failed_user_detail_does_not_drop_the_ranking_row():
    client = FakeClient(
        {
            "leaderboards/global": {
                "entries": [{"rank": 1, "score": 10, "user": {"id": 1, "username": "x"}}]
            },
            "/api2/users/1/": RuntimeError("500"),
            "/api/users/1/": RuntimeError("500"),
        }
    )
    profiles = metaculus.fetch_top(10, client=client, token="", detail_for=1)
    assert profiles[0].handle == "x"


def test_caps_at_two_hundred():
    entries = [{"rank": i, "score": 1000 - i, "user": {"id": i, "username": f"u{i}"}} for i in range(300)]
    client = FakeClient({"leaderboards/global": {"entries": entries}})
    assert len(metaculus.fetch_top(10_000, client=client, token="", detail_for=0)) == metaculus.MAX_PROFILES


def test_adapter_exposes_the_pipeline_interface():
    assert callable(metaculus.fetch_top)
    assert metaculus.name == "metaculus"

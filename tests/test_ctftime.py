from adapters import ctftime
from core.schema import RawProfile


class FakeClient:
    def __init__(self, json_payloads, html=None):
        self.json_payloads = json_payloads
        self.html = html or {}
        self.json_calls = []
        self.html_calls = []

    def get_json(self, url):
        self.json_calls.append(url)
        for fragment, payload in self.json_payloads.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected JSON {url}")

    def get_html(self, url):
        self.html_calls.append(url)
        for fragment, payload in self.html.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        return ""


TOP = {"2026": [{"team_name": "r3kapig", "points": 1589.0, "team_id": 58979}]}
TEAM_JSON = {
    "id": 58979,
    "name": "r3kapig",
    "country": "CN",
    "aliases": ["mini-r3kapig"],
}
TEAM_HTML = """
<a href="/user/3401">stypr</a>
<a href="/user/11460">iamjimyes</a>
<a href="/user/3401">stypr</a>
<p>Site:</p><a href="https://r3kapig.com">r3kapig.com</a>
<a href="https://github.com/r3kapig">org</a>
"""


def test_emits_members_listed_on_the_team_page():
    client = FakeClient(
        {"/top/2026/": TOP, "/teams/58979/": TEAM_JSON},
        html={"/team/58979": TEAM_HTML},
    )
    profiles = ctftime.fetch_top(50, client=client, year=2026)
    assert [p.handle for p in profiles] == ["stypr", "iamjimyes"]
    assert all(p.raw["weak_attribution"] for p in profiles)
    assert all(p.raw["kind"] == "member" for p in profiles)
    assert "https://github.com/r3kapig" in profiles[0].profile_links
    assert profiles[0].country == "CN"
    assert profiles[0].rating == 1589.0
    assert isinstance(profiles[0], RawProfile)


def test_team_row_when_no_members_are_attributed():
    client = FakeClient(
        {"/top/2026/": TOP, "/teams/58979/": TEAM_JSON},
        html={"/team/58979": "<html>no users here</html>"},
    )
    profiles = ctftime.fetch_top(50, client=client, year=2026)
    assert [p.handle for p in profiles] == ["team-58979"]
    assert profiles[0].raw["kind"] == "team"
    assert profiles[0].raw["weak_attribution"] is True


def test_falls_back_to_previous_year():
    client = FakeClient(
        {
            "/top/2026/": {},
            "/top/2025/": {"2025": [{"team_name": "old", "points": 10, "team_id": 1}]},
            "/teams/1/": {"id": 1, "country": "US"},
        },
        html={"/team/1": '<a href="/user/9">alice</a>'},
    )
    profiles = ctftime.fetch_top(10, client=client, year=2026)
    assert profiles[0].handle == "alice"


def test_a_failed_team_page_does_not_abort_the_adapter():
    client = FakeClient(
        {"/top/2026/": TOP, "/teams/58979/": TEAM_JSON},
        html={"/team/58979": RuntimeError("503")},
    )
    profiles = ctftime.fetch_top(10, client=client, year=2026)
    assert profiles[0].handle == "team-58979"


def test_caps_at_max_profiles():
    top = {
        "2026": [
            {"team_name": f"t{i}", "points": 100 - i, "team_id": i} for i in range(40)
        ]
    }
    json_payloads = {"/top/2026/": top}
    html = {}
    for i in range(40):
        json_payloads[f"/teams/{i}/"] = {"id": i, "country": "US"}
        links = "".join(f'<a href="/user/{i}{j}">{i}-{j}</a>' for j in range(20))
        html[f"/team/{i}"] = links
    client = FakeClient(json_payloads, html=html)
    profiles = ctftime.fetch_top(10_000, client=client, year=2026)
    assert len(profiles) == ctftime.MAX_PROFILES


def test_adapter_exposes_the_pipeline_interface():
    assert callable(ctftime.fetch_top)
    assert ctftime.name == "ctftime"

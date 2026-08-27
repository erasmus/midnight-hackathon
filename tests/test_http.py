import pytest
from core.http import HttpClient, USER_AGENT


class FakeResponse:
    def __init__(self, status_code=200, text='{"ok": true}'):
        self.status_code = status_code
        self.text = text


class FakeSession:
    """Stands in for requests.Session, recording what the client asked for."""

    def __init__(self, responses=None):
        self.headers = {}
        self.calls = []
        self._responses = list(responses or [])

    def get(self, url, timeout=None):
        self.calls.append(url)
        if self._responses:
            return self._responses.pop(0)
        return FakeResponse()


def client(tmp_path, session, **kwargs):
    sleeps = []
    c = HttpClient(
        cache_dir=tmp_path / "cache",
        session=session,
        sleep=sleeps.append,
        min_interval=1.0,
        **kwargs,
    )
    return c, sleeps


def test_identical_request_is_served_from_cache(tmp_path):
    session = FakeSession()
    c, _ = client(tmp_path, session)
    first = c.get_json("https://example.com/a")
    second = c.get_json("https://example.com/a")
    assert first == second == {"ok": True}
    assert session.calls == ["https://example.com/a"]


def test_cache_survives_a_new_client_over_the_same_directory(tmp_path):
    session = FakeSession()
    c1, _ = client(tmp_path, session)
    c1.get_json("https://example.com/a")
    c2, _ = client(tmp_path, FakeSession())
    assert c2.get_json("https://example.com/a") == {"ok": True}


def test_different_urls_are_cached_separately(tmp_path):
    session = FakeSession()
    c, _ = client(tmp_path, session)
    c.get_json("https://example.com/a")
    c.get_json("https://example.com/b")
    assert session.calls == ["https://example.com/a", "https://example.com/b"]


def test_second_request_to_the_same_host_waits(tmp_path):
    session = FakeSession()
    c, sleeps = client(tmp_path, session)
    c.get_json("https://example.com/a")
    c.get_json("https://example.com/b")
    assert sleeps and sleeps[0] > 0


def test_first_request_to_a_host_does_not_wait(tmp_path):
    session = FakeSession()
    c, sleeps = client(tmp_path, session)
    c.get_json("https://example.com/a")
    assert sleeps == []


def test_delay_is_tracked_per_host_not_globally(tmp_path):
    session = FakeSession()
    c, sleeps = client(tmp_path, session)
    c.get_json("https://example.com/a")
    c.get_json("https://other.com/a")
    assert sleeps == []


def test_user_agent_identifying_the_project_is_sent(tmp_path):
    session = FakeSession()
    client(tmp_path, session)
    assert "midnight-hackathon" in session.headers["User-Agent"]
    assert session.headers["User-Agent"] == USER_AGENT


def test_server_error_is_retried_once_and_then_succeeds(tmp_path):
    session = FakeSession([FakeResponse(503, "nope"), FakeResponse(200, '{"ok": true}')])
    c, _ = client(tmp_path, session)
    assert c.get_json("https://example.com/a") == {"ok": True}
    assert len(session.calls) == 2


def test_persistent_server_error_raises_after_one_retry(tmp_path):
    session = FakeSession([FakeResponse(500, "boom"), FakeResponse(500, "boom")])
    c, _ = client(tmp_path, session)
    with pytest.raises(RuntimeError):
        c.get_json("https://example.com/a")
    assert len(session.calls) == 2


def test_client_error_is_not_retried(tmp_path):
    session = FakeSession([FakeResponse(404, "missing")])
    c, _ = client(tmp_path, session)
    with pytest.raises(RuntimeError):
        c.get_json("https://example.com/a")
    assert len(session.calls) == 1


def test_failed_responses_are_not_cached(tmp_path):
    session = FakeSession([FakeResponse(404, "missing"), FakeResponse(200, '{"ok": true}')])
    c, _ = client(tmp_path, session)
    with pytest.raises(RuntimeError):
        c.get_json("https://example.com/a")
    assert c.get_json("https://example.com/a") == {"ok": True}


def test_get_html_returns_the_response_body(tmp_path):
    session = FakeSession([FakeResponse(200, "<html>hi</html>")])
    c, _ = client(tmp_path, session)
    assert c.get_html("https://example.com/a") == "<html>hi</html>"


class PostSession(FakeSession):
    def __init__(self, responses=None):
        super().__init__(responses)
        self.posts = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append((url, data, headers))
        self.calls.append(url)
        if self._responses:
            return self._responses.pop(0)
        return FakeResponse()


def test_post_returns_decoded_json(tmp_path):
    session = PostSession([FakeResponse(200, '[{"id": "a"}]')])
    c, _ = client(tmp_path, session)
    assert c.post_json("https://example.com/api/users", "a,b") == [{"id": "a"}]


def test_post_sends_the_request_body(tmp_path):
    session = PostSession()
    c, _ = client(tmp_path, session)
    c.post_json("https://example.com/api/users", "a,b")
    assert session.posts[0][1] == "a,b"


def test_identical_post_is_served_from_cache(tmp_path):
    session = PostSession()
    c, _ = client(tmp_path, session)
    c.post_json("https://example.com/api/users", "a,b")
    c.post_json("https://example.com/api/users", "a,b")
    assert len(session.posts) == 1


def test_posts_with_different_bodies_are_cached_separately(tmp_path):
    session = PostSession()
    c, _ = client(tmp_path, session)
    c.post_json("https://example.com/api/users", "a,b")
    c.post_json("https://example.com/api/users", "c,d")
    assert len(session.posts) == 2


def test_a_post_does_not_collide_with_a_get_on_the_same_url(tmp_path):
    session = PostSession([FakeResponse(200, '{"get": true}'), FakeResponse(200, '{"post": true}')])
    c, _ = client(tmp_path, session)
    assert c.get_json("https://example.com/x") == {"get": True}
    assert c.post_json("https://example.com/x", "body") == {"post": True}


def test_post_respects_the_per_host_delay(tmp_path):
    session = PostSession()
    c, sleeps = client(tmp_path, session)
    c.get_json("https://example.com/a")
    c.post_json("https://example.com/b", "body")
    assert sleeps and sleeps[0] > 0


def test_post_server_error_is_retried_once(tmp_path):
    session = PostSession([FakeResponse(503, "nope"), FakeResponse(200, '{"ok": true}')])
    c, _ = client(tmp_path, session)
    assert c.post_json("https://example.com/a", "b") == {"ok": True}
    assert len(session.posts) == 2


def test_post_accept_header_can_be_overridden(tmp_path):
    session = PostSession()
    c, _ = client(tmp_path, session)
    c.post_json("https://example.com/a", "b", accept="application/x-ndjson")
    assert session.posts[0][2]["Accept"] == "application/x-ndjson"


def test_get_ndjson_parses_one_object_per_line(tmp_path):
    session = FakeSession([FakeResponse(200, '{"id": "a"}\n{"id": "b"}\n')])
    c, _ = client(tmp_path, session)
    assert c.get_ndjson("https://example.com/s") == [{"id": "a"}, {"id": "b"}]


def test_ndjson_ignores_blank_lines(tmp_path):
    session = FakeSession([FakeResponse(200, '{"id": "a"}\n\n\n{"id": "b"}\n')])
    c, _ = client(tmp_path, session)
    assert len(c.get_ndjson("https://example.com/s")) == 2

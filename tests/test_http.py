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


class StreamResponse:
    def __init__(self, chunks=(b"data",), status_code=200):
        self.status_code = status_code
        self._chunks = list(chunks)

    def iter_content(self, chunk_size=None):
        return iter(self._chunks)

    def close(self):
        pass


class StreamSession(FakeSession):
    def __init__(self, responses=None):
        super().__init__(responses)
        self.streamed = []

    def get(self, url, timeout=None, stream=False):
        self.calls.append(url)
        if stream:
            self.streamed.append(url)
        if self._responses:
            return self._responses.pop(0)
        return StreamResponse()


def test_download_writes_the_response_to_disk(tmp_path):
    session = StreamSession([StreamResponse([b"hello ", b"world"])])
    c, _ = client(tmp_path, session)
    path = c.download("https://example.com/f.zip", tmp_path / "f.zip")
    assert path.read_bytes() == b"hello world"


def test_download_streams_rather_than_buffering(tmp_path):
    session = StreamSession()
    c, _ = client(tmp_path, session)
    c.download("https://example.com/f.zip", tmp_path / "f.zip")
    assert session.streamed == ["https://example.com/f.zip"]


def test_an_already_downloaded_file_is_not_refetched(tmp_path):
    session = StreamSession()
    c, _ = client(tmp_path, session)
    dest = tmp_path / "f.zip"
    c.download("https://example.com/f.zip", dest)
    c.download("https://example.com/f.zip", dest)
    assert len(session.calls) == 1


def test_a_download_can_be_forced_to_refresh(tmp_path):
    session = StreamSession()
    c, _ = client(tmp_path, session)
    dest = tmp_path / "f.zip"
    c.download("https://example.com/f.zip", dest)
    c.download("https://example.com/f.zip", dest, refresh=True)
    assert len(session.calls) == 2


def test_download_creates_missing_parent_directories(tmp_path):
    session = StreamSession()
    c, _ = client(tmp_path, session)
    path = c.download("https://example.com/f.zip", tmp_path / "deep" / "nested" / "f.zip")
    assert path.exists()


def test_a_failed_download_raises_and_leaves_no_partial_file(tmp_path):
    session = StreamSession([StreamResponse(status_code=404)])
    c, _ = client(tmp_path, session)
    dest = tmp_path / "f.zip"
    with pytest.raises(RuntimeError):
        c.download("https://example.com/f.zip", dest)
    assert not dest.exists()


def test_download_respects_the_per_host_delay(tmp_path):
    session = StreamSession([FakeResponse(), StreamResponse()])
    c, sleeps = client(tmp_path, session)
    c.get_json("https://example.com/a")
    c.download("https://example.com/f.zip", tmp_path / "f.zip")
    assert sleeps and sleeps[0] > 0


class Clock:
    """A controllable clock that advances exactly as much as we sleep."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def paced_client(tmp_path, session, min_interval=1.0):
    clock = Clock()
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock.sleep(seconds)

    c = HttpClient(cache_dir=tmp_path / "cache", session=session, sleep=sleep,
                   clock=clock, min_interval=min_interval)
    return c, sleeps, clock


def test_consecutive_requests_each_wait_exactly_the_interval(tmp_path):
    session = FakeSession()
    c, sleeps, _ = paced_client(tmp_path, session)
    for i in range(4):
        c.get_json(f"https://example.com/{i}")
    assert sleeps == [1.0, 1.0, 1.0]


def test_the_delay_does_not_grow_with_each_request(tmp_path):
    # Regression: double-counting the sleep made every request wait one second
    # longer than the last, so 50 requests took ~21 minutes instead of ~50s.
    session = FakeSession()
    c, sleeps, _ = paced_client(tmp_path, session)
    for i in range(10):
        c.get_json(f"https://example.com/{i}")
    assert max(sleeps) == 1.0


def test_total_elapsed_time_is_linear_in_the_request_count(tmp_path):
    session = FakeSession()
    c, _, clock = paced_client(tmp_path, session)
    for i in range(10):
        c.get_json(f"https://example.com/{i}")
    assert clock.now == pytest.approx(9.0)


def test_a_slow_caller_does_not_wait_at_all(tmp_path):
    session = FakeSession()
    c, sleeps, clock = paced_client(tmp_path, session)
    c.get_json("https://example.com/a")
    clock.now += 5.0
    c.get_json("https://example.com/b")
    assert sleeps == []

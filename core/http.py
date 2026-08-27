"""Shared HTTP helper (issue #11).

Every adapter and enricher goes through this module, so the politeness
constraint lives in exactly one place:

  * >= 1s between requests to the same host (per-host, not global)
  * on-disk response cache keyed by URL, so re-runs during the hackathon
    don't re-hit anyone's API
  * one retry on 5xx; 4xx fails immediately
  * a User-Agent that identifies the project and its contact
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

USER_AGENT = (
    "midnight-hackathon/0.1 (TechBBQ Hack & Chill; "
    "+https://github.com/erasmus/midnight-hackathon)"
)

DEFAULT_CACHE_DIR = Path(".cache/http")
DEFAULT_MIN_INTERVAL = 1.0
DEFAULT_TIMEOUT = 20.0
NDJSON = "application/x-ndjson"


class HttpError(RuntimeError):
    """Raised when a URL cannot be fetched (after any retry)."""


class HttpClient:
    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session if session is not None else requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep = sleep
        self._clock = clock
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_request_at: dict[str, float] = {}

    # -- public API -----------------------------------------------------

    def get_html(self, url: str) -> str:
        return self._request("GET", url)

    def get_json(self, url: str) -> Any:
        return json.loads(self._request("GET", url))

    def get_ndjson(self, url: str, accept: str = NDJSON) -> list[Any]:
        """Newline-delimited JSON: one object per line, blank lines ignored."""
        text = self._request("GET", url, accept=accept)
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def post_json(self, url: str, data: Any = None, accept: str = "application/json") -> Any:
        """POST for bulk endpoints (e.g. Lichess `/api/users`, 300 ids a call).

        Cached like a GET, but keyed on URL *and* body, so two different
        batches to the same endpoint don't shadow each other.
        """
        return json.loads(self._request("POST", url, data=data, accept=accept))

    def post_ndjson(self, url: str, data: Any = None) -> list[Any]:
        text = self._request("POST", url, data=data, accept=NDJSON)
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def download(self, url: str, dest: str | Path, refresh: bool = False) -> Path:
        """Stream a large file to disk, once.

        Bulk files (the FIDE rating list is ~14MB zipped) don't belong in the
        text cache, and we must never re-download one we already have. Written
        to a temp file first so a failure can't leave a half-file that looks
        cached on the next run.
        """
        dest = Path(dest)
        if dest.exists() and not refresh:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)

        self._respect_rate_limit(urlparse(url).netloc)
        response = self.session.get(url, timeout=self.timeout, stream=True)
        if response.status_code >= 400:
            raise HttpError(f"GET {url} failed with HTTP {response.status_code}")

        partial = dest.with_suffix(dest.suffix + ".part")
        try:
            with open(partial, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    if chunk:
                        handle.write(chunk)
            partial.replace(dest)
        finally:
            partial.unlink(missing_ok=True)
            close = getattr(response, "close", None)
            if close:
                close()
        return dest

    # -- internals ------------------------------------------------------

    def _request(
        self, method: str, url: str, data: Any = None, accept: str | None = None
    ) -> str:
        key = self._cache_key(method, url, data)
        cached = self._read_cache(key)
        if cached is not None:
            return cached
        text = self._fetch_with_retry(method, url, data, accept)
        self._write_cache(key, text)
        return text

    def _fetch_with_retry(
        self, method: str, url: str, data: Any, accept: str | None
    ) -> str:
        response = self._fetch(method, url, data, accept)
        if response.status_code >= 500:
            # One retry, then give up. Transient upstream blips are common;
            # hammering someone's API during a hackathon is not acceptable.
            response = self._fetch(method, url, data, accept)
        if response.status_code >= 400:
            raise HttpError(f"{method} {url} failed with HTTP {response.status_code}")
        return response.text

    def _fetch(self, method: str, url: str, data: Any, accept: str | None):
        self._respect_rate_limit(urlparse(url).netloc)
        if method == "POST":
            headers = {"Accept": accept} if accept else None
            return self.session.post(
                url, data=data, headers=headers, timeout=self.timeout
            )
        return self.session.get(url, timeout=self.timeout)

    def _respect_rate_limit(self, host: str) -> None:
        """Ensure >= min_interval since the last request to this host.

        The recorded timestamp must be the clock reading *after* sleeping, not
        that reading plus the sleep again -- double-counting it makes each
        request wait one interval longer than the last, so the delay grows
        without bound (50 requests took ~21 minutes instead of ~50 seconds).
        """
        last = self._last_request_at.get(host)
        if last is not None:
            wait = self.min_interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at[host] = self._clock()

    def _cache_key(self, method: str, url: str, data: Any = None) -> str:
        body = "" if data is None else str(data)
        return hashlib.sha256(f"{method} {url} {body}".encode("utf-8")).hexdigest()

    def _read_cache(self, key: str) -> str | None:
        path = self.cache_dir / f"{key}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def _write_cache(self, key: str, text: str) -> None:
        (self.cache_dir / f"{key}.txt").write_text(text, encoding="utf-8")


_default_client: HttpClient | None = None


def default_client() -> HttpClient:
    """Process-wide client, so per-host spacing is shared across adapters."""
    global _default_client
    if _default_client is None:
        _default_client = HttpClient()
    return _default_client


def get_json(url: str) -> Any:
    return default_client().get_json(url)


def get_html(url: str) -> str:
    return default_client().get_html(url)


def post_json(url: str, data: Any = None) -> Any:
    return default_client().post_json(url, data)

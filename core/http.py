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
        return self._get_text(url)

    def get_json(self, url: str) -> Any:
        return json.loads(self._get_text(url))

    # -- internals ------------------------------------------------------

    def _get_text(self, url: str) -> str:
        cached = self._read_cache(url)
        if cached is not None:
            return cached
        text = self._fetch_with_retry(url)
        self._write_cache(url, text)
        return text

    def _fetch_with_retry(self, url: str) -> str:
        response = self._fetch(url)
        if response.status_code >= 500:
            # One retry, then give up. Transient upstream blips are common;
            # hammering someone's API during a hackathon is not acceptable.
            response = self._fetch(url)
        if response.status_code >= 400:
            raise HttpError(f"GET {url} failed with HTTP {response.status_code}")
        return response.text

    def _fetch(self, url: str):
        self._respect_rate_limit(urlparse(url).netloc)
        return self.session.get(url, timeout=self.timeout)

    def _respect_rate_limit(self, host: str) -> None:
        now = self._clock()
        last = self._last_request_at.get(host)
        if last is not None:
            wait = self.min_interval - (now - last)
            if wait > 0:
                self._sleep(wait)
                now = self._clock() + wait
        self._last_request_at[host] = now

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.txt"

    def _read_cache(self, url: str) -> str | None:
        path = self._cache_path(url)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def _write_cache(self, url: str, text: str) -> None:
        self._cache_path(url).write_text(text, encoding="utf-8")


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

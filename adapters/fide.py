"""FIDE adapter (issue #15).

One monthly file, no API: the standard rating list XML, downloaded once and
cached on disk. Parsed with `iterparse` and cleared as we go, so a 14MB zip
(~1.2M players) costs constant memory rather than a gigabyte of DOM.

This adapter has two jobs:

  * `fetch_top(n)` -- candidates, same contract as every other adapter:
    everyone >=2500, plus anyone >=2300 born >=1998 (the young-and-strong
    tail this project is actually looking for).
  * `load_index()` -- the join table for #21, keyed by `(title, name)`. This
    deliberately covers *every* titled player, not just the top slice: the
    join needs to answer "is this Lichess GM in the FIDE file?" for players
    far below any shortlist cutoff. It is a local file scan, not requests, so
    the top-of-tail request budget is untouched.

`birth_year` is why this source matters: it is the pipeline's only
age-verification oracle, so rows without one are dropped rather than guessed.

Consent-by-disclosure: the FIDE rating list is a published, official record of
competitive results. Nothing here is scraped from a private profile.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from core.http import DEFAULT_CACHE_DIR, default_client
from core.schema import RawProfile

name = "fide"

RATING_LIST_URL = "https://ratings.fide.com/download/standard_rating_list_xml.zip"
PROFILE_URL = "https://ratings.fide.com/profile/{fideid}"
CACHE_PATH = Path(DEFAULT_CACHE_DIR).parent / "fide" / "standard_rating_list_xml.zip"

MAX_PROFILES = 500
STRONG_RATING = 2500
YOUNG_RATING = 2300
YOUNG_BORN_FROM = 1998

_PUNCTUATION = re.compile(r"[^a-z0-9\s]")


def normalise_name(name_: str) -> str:
    """`"Carlsen, Magnus"` -> `"magnus carlsen"`, accent- and punctuation-free.

    Used as the join key, so it must be stable across the different spellings
    the same person uses on FIDE and on a chess site.
    """
    text = (name_ or "").strip()
    if "," in text:
        last, _, first = text.partition(",")
        text = f"{first.strip()} {last.strip()}"
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCTUATION.sub(" ", text.lower())
    return " ".join(text.split())


def _int(value: str | None) -> int | None:
    try:
        return int((value or "").strip())
    except (TypeError, ValueError):
        return None


def _rating_list_path(client=None, path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    client = client or default_client()
    return Path(client.download(RATING_LIST_URL, CACHE_PATH))


def iter_players(path: str | Path):
    """Stream `<player>` records at roughly constant memory.

    `element.clear()` alone is not enough: the root keeps a reference to every
    (now empty) `<player>` it has seen, so the list still grows to ~1.2M
    entries. Dropping them from the root as we go is what actually bounds the
    footprint.
    """
    with zipfile.ZipFile(path) as archive:
        inner = archive.namelist()[0]
        with archive.open(inner) as handle:
            root = None
            for event, element in ElementTree.iterparse(handle, events=("start", "end")):
                if root is None:
                    root = element
                    continue
                if event != "end" or element.tag != "player":
                    continue
                yield {child.tag: (child.text or "").strip() for child in element}
                element.clear()
                root.clear()


def _is_candidate(rating: int, birth_year: int) -> bool:
    if rating >= STRONG_RATING:
        return True
    return rating >= YOUNG_RATING and birth_year >= YOUNG_BORN_FROM


def fetch_top(
    n: int = MAX_PROFILES,
    client=None,
    path: str | Path | None = None,
) -> list[RawProfile]:
    source = _rating_list_path(client, path)
    fetched_at = datetime.now(timezone.utc).isoformat()

    candidates: list[RawProfile] = []
    for record in iter_players(source):
        rating = _int(record.get("rating"))
        birth_year = _int(record.get("birthday"))
        # birth_year is the age oracle; a row without one cannot be used.
        if rating is None or not birth_year:
            continue
        if not _is_candidate(rating, birth_year):
            continue
        fideid = record.get("fideid") or ""
        candidates.append(
            RawProfile(
                platform=name,
                handle=fideid,
                display_name=_readable_name(record.get("name")),
                url=PROFILE_URL.format(fideid=fideid),
                rating=rating,
                rank_pct=None,  # a rating list is not a ranked percentile table
                country=record.get("country") or None,
                birth_year=birth_year,
                raw={
                    "title": record.get("title") or None,
                    "women_title": record.get("w_title") or None,
                    "sex": record.get("sex") or None,
                    "games": _int(record.get("games")),
                    "fide_name": record.get("name"),
                },
                fetched_at=fetched_at,
            )
        )

    candidates.sort(key=lambda p: (-(p.rating or 0), p.handle))
    return candidates[: min(n, MAX_PROFILES)]


def _readable_name(fide_name: str | None) -> str:
    text = (fide_name or "").strip()
    if "," in text:
        last, _, first = text.partition(",")
        return f"{first.strip()} {last.strip()}".strip()
    return text


def load_index(client=None, path: str | Path | None = None) -> dict[tuple[str, str], dict]:
    """`(title, normalised_name) -> record` for every titled player (#21).

    Collisions are marked `ambiguous` rather than silently overwritten: two
    different GMs sharing a name must not produce a confident join.
    """
    source = _rating_list_path(client, path)
    index: dict[tuple[str, str], dict] = {}

    for record in iter_players(source):
        title = (record.get("title") or "").strip()
        if not title:
            continue
        key = (title, normalise_name(record.get("name")))
        if key in index:
            index[key]["ambiguous"] = True
            continue
        index[key] = {
            "fideid": record.get("fideid"),
            "name": _readable_name(record.get("name")),
            "fide_name": record.get("name"),
            "title": title,
            "country": record.get("country") or None,
            "rating": _int(record.get("rating")),
            "birth_year": _int(record.get("birthday")),
            "ambiguous": False,
        }
    return index

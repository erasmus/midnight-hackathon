"""Kaggle adapter (issue #12).

Reads Meta Kaggle (`Users.csv` + `UserAchievements.csv`) as a stream — those
files are huge and must never be loaded whole. Competitions Masters and
Grandmasters only (AchievementType = Competitions, Tier ≥ 3).

Profile-page HTML is fetched only for the top slice, through the shared HTTP
client, so GitHub/LinkedIn/Twitter self-links land in `profile_links`.

Put the CSVs in `data/meta-kaggle/` (or `$META_KAGGLE_DIR`). Missing files
log and return [] so a laptop without the dump doesn't sink the pipeline.
"""

from __future__ import annotations

import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from core.http import default_client
from core.schema import RawProfile

name = "kaggle"

PROFILE_URL = "https://www.kaggle.com/{handle}"
DEFAULT_DATA_DIR = Path("data/meta-kaggle")
USERS_CSV = "Users.csv"
ACHIEVEMENTS_CSV = "UserAchievements.csv"

MAX_PROFILES = 500
# UserAchievements.Tier: 0 Novice, 1 Contributor, 2 Expert, 3 Master, 4 Grandmaster
TIER_MASTER = 3
TIER_NAMES = {3: "Master", 4: "Grandmaster"}
DEFAULT_PROFILE_FOR = 50

URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:github\.com|linkedin\.com/in|twitter\.com|x\.com)/[^\s\"'<>]+",
    re.I,
)


def _data_dir(data_dir: str | Path | None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    env = os.environ.get("META_KAGGLE_DIR")
    return Path(env) if env else DEFAULT_DATA_DIR


def _int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _stream_masters(achievements_path: Path) -> dict[str, dict]:
    """UserId -> achievement row. One pass, only Masters+ in memory."""
    masters: dict[str, dict] = {}
    with achievements_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("AchievementType") != "Competitions":
                continue
            tier = _int(row.get("Tier"), 0)
            if tier < TIER_MASTER:
                continue
            user_id = row.get("UserId")
            if not user_id:
                continue
            prev = masters.get(user_id)
            if prev is None or tier > _int(prev.get("Tier"), 0):
                masters[user_id] = row
    return masters


def _profile_links(html: str) -> list[str]:
    found: list[str] = []
    for url in URL_PATTERN.findall(html or ""):
        url = url.rstrip(").,;")
        if url not in found:
            found.append(url)
    return found


def fetch_top(
    n: int = MAX_PROFILES,
    client=None,
    data_dir: str | Path | None = None,
    profile_for: int | None = None,
) -> list[RawProfile]:
    client = client or default_client()
    profile_for = DEFAULT_PROFILE_FOR if profile_for is None else profile_for
    folder = _data_dir(data_dir)
    users_path = folder / USERS_CSV
    achievements_path = folder / ACHIEVEMENTS_CSV
    if not users_path.exists() or not achievements_path.exists():
        print(
            f"  ! kaggle: {USERS_CSV} / {ACHIEVEMENTS_CSV} not in {folder} "
            "(download Meta Kaggle once). Returning no profiles."
        )
        return []

    masters = _stream_masters(achievements_path)
    fetched_at = datetime.now(timezone.utc).isoformat()
    ranked: list[tuple[dict, dict]] = []

    with users_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for user in reader:
            achievement = masters.get(user.get("Id", ""))
            if achievement is None:
                continue
            ranked.append((user, achievement))

    def sort_key(pair: tuple[dict, dict]):
        user, ach = pair
        gold = _int(ach.get("TotalGold"), 0) or 0
        tier = _int(ach.get("Tier"), 0) or 0
        highest = _int(ach.get("HighestRanking"), 10**9) or 10**9
        return (-tier, -gold, highest, user.get("UserName") or "")

    ranked.sort(key=sort_key)
    ranked = ranked[: min(n, MAX_PROFILES)]

    profiles: list[RawProfile] = []
    for i, (user, ach) in enumerate(ranked):
        handle = user.get("UserName") or user.get("Id")
        gold = _int(ach.get("TotalGold"), 0)
        html = ""
        if i < profile_for and user.get("UserName"):
            try:
                html = client.get_html(PROFILE_URL.format(handle=handle))
            except Exception as exc:  # noqa: BLE001
                print(f"  ! kaggle profile page unavailable for {handle}: {exc}")
        tier = _int(ach.get("Tier"), 0) or 0
        profiles.append(
            RawProfile(
                platform=name,
                handle=str(handle),
                display_name=user.get("DisplayName") or handle,
                url=PROFILE_URL.format(handle=handle),
                rating=float(gold) if gold is not None else None,
                rank_pct=None,
                profile_links=_profile_links(html),
                country=user.get("Country") or None,
                raw={
                    "metric_name": "kaggle_comp_medals_gold",
                    "tier": tier,
                    "tier_name": TIER_NAMES.get(tier, str(tier)),
                    "highest_rank": _int(ach.get("HighestRanking")),
                    "current_rank": _int(ach.get("CurrentRanking")),
                    "gold": gold,
                    "silver": _int(ach.get("TotalSilver")),
                    "bronze": _int(ach.get("TotalBronze")),
                    "user_id": user.get("Id"),
                },
                fetched_at=fetched_at,
            )
        )
    return profiles

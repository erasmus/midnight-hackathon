import csv
from pathlib import Path

from adapters import kaggle
from core.schema import RawProfile


class FakeClient:
    def __init__(self, pages=None):
        self.pages = pages or {}
        self.html_calls = []

    def get_html(self, url):
        self.html_calls.append(url)
        for handle, html in self.pages.items():
            if handle in url:
                return html
        return ""


def write_csvs(folder: Path, users, achievements):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "Users.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Id", "UserName", "DisplayName", "Country"])
        writer.writeheader()
        writer.writerows(users)
    with (folder / "UserAchievements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Id",
                "UserId",
                "AchievementType",
                "Tier",
                "TotalGold",
                "TotalSilver",
                "TotalBronze",
                "HighestRanking",
                "CurrentRanking",
            ],
        )
        writer.writeheader()
        writer.writerows(achievements)


def fetch(folder, client=None, **kw):
    kw.setdefault("profile_for", 0)
    return kaggle.fetch_top(client=client or FakeClient(), data_dir=folder, **kw)


def test_missing_dump_returns_empty(tmp_path):
    assert fetch(tmp_path / "nope") == []


def test_stream_filters_competitions_masters(tmp_path):
    write_csvs(
        tmp_path,
        [
            {"Id": "1", "UserName": "gm", "DisplayName": "Grace Master", "Country": "US"},
            {"Id": "2", "UserName": "novice", "DisplayName": "Novice", "Country": "US"},
            {"Id": "3", "UserName": "nb", "DisplayName": "Notebook Only", "Country": "US"},
        ],
        [
            {"Id": "a", "UserId": "1", "AchievementType": "Competitions", "Tier": "4",
             "TotalGold": "11", "TotalSilver": "2", "TotalBronze": "0",
             "HighestRanking": "40", "CurrentRanking": "41"},
            {"Id": "b", "UserId": "2", "AchievementType": "Competitions", "Tier": "1",
             "TotalGold": "0", "TotalSilver": "0", "TotalBronze": "0",
             "HighestRanking": "", "CurrentRanking": ""},
            {"Id": "c", "UserId": "3", "AchievementType": "Notebooks", "Tier": "4",
             "TotalGold": "9", "TotalSilver": "0", "TotalBronze": "0",
             "HighestRanking": "1", "CurrentRanking": "1"},
        ],
    )
    profiles = fetch(tmp_path)
    assert [p.handle for p in profiles] == ["gm"]
    assert profiles[0].display_name == "Grace Master"
    assert profiles[0].raw["metric_name"] == "kaggle_comp_medals_gold"
    assert profiles[0].raw["tier"] == 4
    assert profiles[0].rating == 11
    assert profiles[0].raw["highest_rank"] == 40
    assert profiles[0].platform == "kaggle"
    assert isinstance(profiles[0], RawProfile)


def test_masters_are_included(tmp_path):
    write_csvs(
        tmp_path,
        [{"Id": "1", "UserName": "m", "DisplayName": "M", "Country": "GB"}],
        [{"Id": "a", "UserId": "1", "AchievementType": "Competitions", "Tier": "3",
          "TotalGold": "3", "TotalSilver": "1", "TotalBronze": "0",
          "HighestRanking": "200", "CurrentRanking": "210"}],
    )
    assert [p.handle for p in fetch(tmp_path)] == ["m"]


def test_never_returns_more_than_the_platform_cap(tmp_path):
    users = [{"Id": str(i), "UserName": f"u{i}", "DisplayName": f"U{i}", "Country": ""} for i in range(600)]
    ach = [
        {"Id": str(i), "UserId": str(i), "AchievementType": "Competitions", "Tier": "4",
         "TotalGold": str(600 - i), "TotalSilver": "0", "TotalBronze": "0",
         "HighestRanking": str(i + 1), "CurrentRanking": str(i + 1)}
        for i in range(600)
    ]
    write_csvs(tmp_path, users, ach)
    assert len(fetch(tmp_path, n=10_000)) == kaggle.MAX_PROFILES


def test_profile_pages_are_only_fetched_for_the_top_slice(tmp_path):
    write_csvs(
        tmp_path,
        [
            {"Id": "1", "UserName": "a", "DisplayName": "A", "Country": ""},
            {"Id": "2", "UserName": "b", "DisplayName": "B", "Country": ""},
        ],
        [
            {"Id": "a", "UserId": "1", "AchievementType": "Competitions", "Tier": "4",
             "TotalGold": "5", "TotalSilver": "0", "TotalBronze": "0",
             "HighestRanking": "1", "CurrentRanking": "1"},
            {"Id": "b", "UserId": "2", "AchievementType": "Competitions", "Tier": "4",
             "TotalGold": "4", "TotalSilver": "0", "TotalBronze": "0",
             "HighestRanking": "2", "CurrentRanking": "2"},
        ],
    )
    client = FakeClient(pages={"a": '<a href="https://github.com/alice">gh</a>'})
    profiles = fetch(tmp_path, client=client, profile_for=1)
    assert client.html_calls == ["https://www.kaggle.com/a"]
    assert profiles[0].profile_links == ["https://github.com/alice"]
    assert profiles[1].profile_links == []


def test_a_failed_profile_fetch_keeps_the_row(tmp_path):
    write_csvs(
        tmp_path,
        [{"Id": "1", "UserName": "a", "DisplayName": "A", "Country": ""}],
        [{"Id": "a", "UserId": "1", "AchievementType": "Competitions", "Tier": "4",
          "TotalGold": "1", "TotalSilver": "0", "TotalBronze": "0",
          "HighestRanking": "1", "CurrentRanking": "1"}],
    )

    class Boom(FakeClient):
        def get_html(self, url):
            raise RuntimeError("429")

    profiles = fetch(tmp_path, client=Boom(), profile_for=1)
    assert profiles[0].handle == "a"


def test_adapter_exposes_the_pipeline_interface():
    assert callable(kaggle.fetch_top)
    assert kaggle.name == "kaggle"

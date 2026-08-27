import zipfile

import pytest

from adapters import fide
from core.schema import RawProfile

PLAYER = """<player>
<fideid>{fideid}</fideid><name>{name}</name><country>{country}</country>
<sex>M</sex><title>{title}</title><w_title></w_title><o_title></o_title>
<foa_title></foa_title><rating>{rating}</rating><games>10</games><k>10</k>
<birthday>{birthday}</birthday><flag></flag>
</player>"""


def make_zip(tmp_path, players, name="fide.zip"):
    xml = "<playerslist>\n" + "\n".join(players) + "\n</playerslist>"
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("standard_rating_list.xml", xml)
    return path


def player(fideid="1", name="Carlsen, Magnus", country="NOR", title="GM",
           rating=2839, birthday=1990):
    return PLAYER.format(fideid=fideid, name=name, country=country, title=title,
                         rating=rating, birthday=birthday)


class FakeClient:
    def __init__(self, path):
        self.path = path
        self.downloads = []

    def download(self, url, dest, refresh=False):
        self.downloads.append(url)
        return self.path


def fetch(tmp_path, players, n=500, **kw):
    path = make_zip(tmp_path, players)
    return fide.fetch_top(n, client=FakeClient(path), **kw)


def test_players_are_parsed_into_raw_profiles(tmp_path):
    profiles = fetch(tmp_path, [player()])
    assert len(profiles) == 1
    assert isinstance(profiles[0], RawProfile)
    assert profiles[0].platform == "fide"


def test_the_fide_id_is_the_handle(tmp_path):
    (p,) = fetch(tmp_path, [player(fideid="1503014")])
    assert p.handle == "1503014"


def test_names_are_reordered_from_last_comma_first(tmp_path):
    (p,) = fetch(tmp_path, [player(name="Carlsen, Magnus")])
    assert p.display_name == "Magnus Carlsen"


def test_a_name_without_a_comma_is_left_alone(tmp_path):
    (p,) = fetch(tmp_path, [player(name="A Arbhin Vanniarajan")])
    assert p.display_name == "A Arbhin Vanniarajan"


def test_birth_year_is_populated(tmp_path):
    (p,) = fetch(tmp_path, [player(birthday=1990)])
    assert p.birth_year == 1990


def test_rows_without_a_birth_year_are_dropped(tmp_path):
    profiles = fetch(tmp_path, [player(fideid="1", birthday=0),
                                player(fideid="2", birthday="")])
    assert profiles == []


def test_every_returned_row_has_a_birth_year(tmp_path):
    profiles = fetch(tmp_path, [player(fideid="1"), player(fideid="2", birthday=2001)])
    assert all(p.birth_year for p in profiles)


def test_title_country_and_rating_are_captured(tmp_path):
    (p,) = fetch(tmp_path, [player(title="GM", country="NOR", rating=2839)])
    assert p.raw["title"] == "GM"
    assert p.country == "NOR"
    assert p.rating == 2839


def test_a_row_with_no_rating_is_skipped(tmp_path):
    assert fetch(tmp_path, [player(rating="")]) == []


def test_profile_url_points_at_the_public_fide_page(tmp_path):
    (p,) = fetch(tmp_path, [player(fideid="1503014")])
    assert p.url == "https://ratings.fide.com/profile/1503014"


def test_fetched_at_is_stamped(tmp_path):
    (p,) = fetch(tmp_path, [player()])
    assert p.fetched_at


def test_players_at_or_above_2500_are_included(tmp_path):
    profiles = fetch(tmp_path, [player(fideid="1", rating=2500, birthday=1970)])
    assert len(profiles) == 1


def test_players_below_2500_are_excluded_when_not_young(tmp_path):
    assert fetch(tmp_path, [player(rating=2499, birthday=1970)]) == []


def test_young_players_are_included_from_2300(tmp_path):
    profiles = fetch(tmp_path, [player(rating=2300, birthday=1998)])
    assert len(profiles) == 1


def test_young_players_below_2300_are_excluded(tmp_path):
    assert fetch(tmp_path, [player(rating=2299, birthday=2005)]) == []


def test_older_players_below_2500_are_excluded_even_at_2400(tmp_path):
    assert fetch(tmp_path, [player(rating=2400, birthday=1997)]) == []


def test_results_are_ordered_by_rating_descending(tmp_path):
    profiles = fetch(tmp_path, [player(fideid="a", rating=2600),
                                player(fideid="b", rating=2800)])
    assert [p.handle for p in profiles] == ["b", "a"]


def test_requested_count_caps_the_result(tmp_path):
    profiles = fetch(tmp_path, [player(fideid="a", rating=2600),
                                player(fideid="b", rating=2800)], n=1)
    assert [p.handle for p in profiles] == ["b"]


def test_never_returns_more_than_the_platform_cap(tmp_path):
    many = [player(fideid=str(i), rating=2500 + i % 300) for i in range(600)]
    assert len(fetch(tmp_path, many, n=10_000)) == fide.MAX_PROFILES


def test_download_targets_the_official_fide_url(tmp_path):
    path = make_zip(tmp_path, [player()])
    client = FakeClient(path)
    fide.fetch_top(10, client=client)
    assert client.downloads == [fide.RATING_LIST_URL]


def test_the_index_is_keyed_by_title_and_normalised_name(tmp_path):
    path = make_zip(tmp_path, [player(name="Carlsen, Magnus", title="GM")])
    index = fide.load_index(client=FakeClient(path))
    assert ("GM", "magnus carlsen") in index


def test_the_index_holds_the_birth_year_the_join_needs(tmp_path):
    path = make_zip(tmp_path, [player(name="Carlsen, Magnus", birthday=1990)])
    index = fide.load_index(client=FakeClient(path))
    assert index[("GM", "magnus carlsen")]["birth_year"] == 1990


def test_untitled_players_are_not_in_the_join_index(tmp_path):
    path = make_zip(tmp_path, [player(title="")])
    assert fide.load_index(client=FakeClient(path)) == {}


def test_the_index_covers_titled_players_below_the_candidate_cutoff(tmp_path):
    path = make_zip(tmp_path, [player(name="Weak, Player", title="IM", rating=2100,
                                      birthday=1980)])
    index = fide.load_index(client=FakeClient(path))
    assert ("IM", "player weak") in index


def test_ambiguous_index_entries_are_marked_not_silently_overwritten(tmp_path):
    path = make_zip(tmp_path, [
        player(fideid="1", name="Smith, John", title="GM"),
        player(fideid="2", name="Smith, John", title="GM"),
    ])
    index = fide.load_index(client=FakeClient(path))
    assert index[("GM", "john smith")]["ambiguous"] is True


def test_an_unambiguous_entry_is_not_marked_ambiguous(tmp_path):
    path = make_zip(tmp_path, [player(name="Carlsen, Magnus", title="GM")])
    index = fide.load_index(client=FakeClient(path))
    assert index[("GM", "magnus carlsen")]["ambiguous"] is False


def test_normalise_name_reorders_and_lowercases():
    assert fide.normalise_name("Carlsen, Magnus") == "magnus carlsen"


def test_normalise_name_strips_accents():
    assert fide.normalise_name("Ivanchuk, Vasyl'") == "vasyl ivanchuk"


def test_normalise_name_collapses_whitespace():
    assert fide.normalise_name("  Carlsen,   Magnus  ") == "magnus carlsen"


def test_normalise_name_drops_punctuation():
    assert fide.normalise_name("Nepomniachtchi, Ian-Alexander") == "ian alexander nepomniachtchi"


def test_adapter_exposes_the_pipeline_interface():
    assert callable(fide.fetch_top)
    assert fide.name == "fide"

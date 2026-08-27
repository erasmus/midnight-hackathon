import csv

import pytest

from core.outputs import SHORTLIST_COLUMNS, SHORTLIST_SIZE, key_achievement, write_shortlist
from core.schema import Person, RawProfile, Scores


def prof(platform="codeforces", rating=3000, rank_pct=99.9, raw=None, **kw):
    return RawProfile(platform=platform, handle="x", rating=rating,
                      rank_pct=rank_pct, raw=raw or {}, **kw)


def person(pid="codeforces:x", name="Ada Lovelace", links=None, profiles=None, **kw):
    return Person(id=pid, display_name=name, profiles=profiles or [prof()],
                  links=links or {}, evidence=kw.pop("evidence", ["e"]) if links else [], **kw)


def scores(pid="codeforces:x", composite=80.0, excluded=False, reasons=None, **kw):
    return Scores(person_id=pid, outlierness=90.0, trajectory=70.0,
                  addressability=45, composite=composite, excluded=excluded,
                  exclusion_reasons=reasons or (["r"] if excluded else []), **kw)


def read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_a_csv_file_is_written(tmp_path):
    path = write_shortlist([person()], [scores()], tmp_path)
    assert path.exists() and path.suffix == ".csv"


def test_one_row_per_person(tmp_path):
    people = [person(pid=f"p{i}") for i in range(3)]
    ss = [scores(pid=f"p{i}") for i in range(3)]
    assert len(read(write_shortlist(people, ss, tmp_path))) == 3


def test_the_expected_columns_are_present(tmp_path):
    rows = read(write_shortlist([person()], [scores()], tmp_path))
    assert list(rows[0].keys()) == list(SHORTLIST_COLUMNS)


def test_excluded_people_never_appear(tmp_path):
    people = [person(pid="in"), person(pid="out")]
    ss = [scores(pid="in"), scores(pid="out", excluded=True)]
    rows = read(write_shortlist(people, ss, tmp_path))
    assert [r["person_id"] for r in rows] == ["in"]


def test_rows_are_ordered_by_composite_descending(tmp_path):
    people = [person(pid="lo"), person(pid="hi")]
    ss = [scores(pid="lo", composite=10.0), scores(pid="hi", composite=90.0)]
    rows = read(write_shortlist(people, ss, tmp_path))
    assert [r["person_id"] for r in rows] == ["hi", "lo"]


def test_only_the_top_twenty_are_written(tmp_path):
    people = [person(pid=f"p{i}") for i in range(30)]
    ss = [scores(pid=f"p{i}", composite=float(i)) for i in range(30)]
    assert len(read(write_shortlist(people, ss, tmp_path))) == SHORTLIST_SIZE


def test_evidence_is_readable_not_json(tmp_path):
    p = person(links={"github": "https://github.com/ada"})
    p.evidence = ["codeforces lists github.com/ada", "second reason"]
    rows = read(write_shortlist([p], [scores()], tmp_path))
    assert rows[0]["evidence"] == "codeforces lists github.com/ada; second reason"
    assert "{" not in rows[0]["evidence"]


def test_links_are_readable(tmp_path):
    p = person(links={"github": "https://github.com/ada", "linkedin": "https://l/in/ada"})
    rows = read(write_shortlist([p], [scores()], tmp_path))
    assert "https://github.com/ada" in rows[0]["links"]
    assert "{" not in rows[0]["links"]


def test_domains_are_listed(tmp_path):
    p = person(profiles=[prof("codeforces"), prof("lichess")])
    rows = read(write_shortlist([p], [scores()], tmp_path))
    assert "chess" in rows[0]["domains"] and "competitive_programming" in rows[0]["domains"]


def test_flags_are_rendered(tmp_path):
    rows = read(write_shortlist([person()], [scores(flags=["single_source"])], tmp_path))
    assert rows[0]["flags"] == "single_source"


def test_sub_scores_and_composite_are_written(tmp_path):
    rows = read(write_shortlist([person()], [scores()], tmp_path))
    assert rows[0]["outlierness"] == "90.0"
    assert rows[0]["composite"] == "80.0"


def test_a_person_without_scores_is_skipped(tmp_path):
    rows = read(write_shortlist([person(pid="a"), person(pid="b")], [scores(pid="a")], tmp_path))
    assert [r["person_id"] for r in rows] == ["a"]


def test_the_file_opens_cleanly_with_a_header(tmp_path):
    path = write_shortlist([person()], [scores()], tmp_path)
    with open(path, encoding="utf-8") as handle:
        assert handle.readline().startswith("rank,person_id,")


def test_unicode_names_survive_the_round_trip(tmp_path):
    rows = read(write_shortlist([person(name="Paweł Teclaf")], [scores()], tmp_path))
    assert rows[0]["name"] == "Paweł Teclaf"


def test_an_empty_shortlist_still_writes_a_header(tmp_path):
    path = write_shortlist([], [], tmp_path)
    with open(path, encoding="utf-8") as handle:
        assert handle.readline().strip().startswith("rank,person_id")


# -- key achievement -------------------------------------------------------

def test_the_key_achievement_names_the_strongest_platform():
    p = person(profiles=[prof("codeforces", rating=3400, rank_pct=99.99)])
    assert "codeforces" in key_achievement(p).lower()


def test_the_key_achievement_includes_the_rating():
    p = person(profiles=[prof("codeforces", rating=3400, rank_pct=99.99)])
    assert "3400" in key_achievement(p)


def test_the_key_achievement_mentions_a_title_when_present():
    p = person(profiles=[prof("fide", rating=2700, rank_pct=None, raw={"title": "GM"})])
    assert "GM" in key_achievement(p)


def test_a_person_with_no_profiles_has_no_achievement():
    p = Person(id="x", profiles=[])
    assert key_achievement(p) == ""


def test_write_outputs_produces_a_shortlist_and_dossiers(tmp_path):
    from core.outputs import write_outputs
    p = person()
    paths = write_outputs([p], [scores()], tmp_path)
    names = [x.name for x in paths]
    assert "shortlist.csv" in names
    assert any(n.startswith("dossier-") for n in names)


def test_no_dossier_is_written_for_an_excluded_person(tmp_path):
    from core.outputs import write_outputs
    paths = write_outputs([person()], [scores(excluded=True)], tmp_path)
    assert not any(x.name.startswith("dossier-") for x in paths)


def test_dossiers_are_capped_to_the_shortlist(tmp_path):
    from core.outputs import write_outputs
    people = [person(pid=f"p{i}") for i in range(30)]
    ss = [scores(pid=f"p{i}", composite=float(i)) for i in range(30)]
    paths = write_outputs(people, ss, tmp_path)
    assert sum(1 for x in paths if x.name.startswith("dossier-")) == SHORTLIST_SIZE

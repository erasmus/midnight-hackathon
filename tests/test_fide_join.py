import pytest

from core.fide_join import MIN_SIMILARITY, build_buckets, find_match
from core.resolve import resolve
from core.schema import RawProfile


def record(name="Magnus Carlsen", title="GM", birth_year=1990, fideid="1503014",
           ambiguous=False, rating=2839):
    return {"fideid": fideid, "name": name, "fide_name": name, "title": title,
            "country": "NOR", "rating": rating, "birth_year": birth_year,
            "ambiguous": ambiguous}


def index(*records):
    from adapters.fide import normalise_name
    return {(r["title"], normalise_name(r["name"])): r for r in records}


def li(handle="DrNykterstein", name="Magnus Carlsen", title="GM", **kw):
    raw = kw.pop("raw", {})
    raw.setdefault("title", title)
    return RawProfile(platform="lichess", handle=handle, display_name=name, raw=raw, **kw)


# -- matching --------------------------------------------------------------

def test_an_exact_title_and_name_match_is_found():
    match = find_match("GM", "Magnus Carlsen", build_buckets(index(record())))
    assert match.record["fideid"] == "1503014"


def test_a_near_identical_name_still_matches():
    match = find_match("GM", "Magnus Carlson", build_buckets(index(record())))
    assert match is not None


def test_similarity_is_reported():
    match = find_match("GM", "Magnus Carlsen", build_buckets(index(record())))
    assert match.similarity == pytest.approx(1.0)


def test_a_different_name_does_not_match():
    assert find_match("GM", "Hikaru Nakamura", build_buckets(index(record()))) is None


def test_a_name_below_the_threshold_does_not_match():
    buckets = build_buckets(index(record()))
    assert find_match("GM", "Magnus Andersen", buckets) is None


def test_the_threshold_is_nine_tenths():
    assert MIN_SIMILARITY == 0.9


def test_a_different_title_never_matches_even_with_the_same_name():
    # Exact title match is required: an IM is not the GM of the same name.
    assert find_match("IM", "Magnus Carlsen", build_buckets(index(record()))) is None


def test_an_absent_title_never_matches():
    assert find_match(None, "Magnus Carlsen", build_buckets(index(record()))) is None


def test_an_absent_name_never_matches():
    assert find_match("GM", None, build_buckets(index(record()))) is None


def test_an_ambiguous_fide_entry_is_refused():
    buckets = build_buckets(index(record(ambiguous=True)))
    assert find_match("GM", "Magnus Carlsen", buckets) is None


def test_the_best_candidate_wins_when_several_are_close():
    buckets = build_buckets(index(
        record(name="Magnus Carlsen", fideid="1"),
        record(name="Magnus Carlsson", fideid="2"),
    ))
    assert find_match("GM", "Magnus Carlsen", buckets).record["fideid"] == "1"


def test_name_order_does_not_matter():
    match = find_match("GM", "Carlsen, Magnus", build_buckets(index(record())))
    assert match is not None


# -- integration through resolve ------------------------------------------

class NoGitHub:
    def get_json(self, url):
        raise RuntimeError("404")


def run(profiles, idx):
    return resolve(profiles, github_client=NoGitHub(), github_for=0, fide_index=idx)


def test_a_joined_player_gains_a_birth_year():
    (person,) = run([li()], index(record()))
    assert person.birth_year == 1990


def test_the_join_is_explained_in_the_evidence():
    (person,) = run([li()], index(record()))
    assert any("FIDE" in e for e in person.evidence)


def test_the_evidence_names_the_similarity_and_title():
    (person,) = run([li()], index(record()))
    joined = next(e for e in person.evidence if "FIDE" in e)
    assert "GM" in joined and "0.9" in joined or "1.0" in joined


def test_an_untitled_player_is_not_joined():
    (person,) = run([li(title=None)], index(record()))
    assert person.birth_year is None


def test_a_non_matching_player_keeps_no_birth_year():
    (person,) = run([li(name="Somebody Else")], index(record()))
    assert person.birth_year is None


def test_a_near_miss_is_recorded_but_not_merged():
    (person,) = run([li(name="Magnus Andersen")], index(record()))
    assert person.birth_year is None
    assert any("near" in n.lower() for n in person.weak_matches)


def test_a_declared_birth_year_is_not_overwritten_by_the_join():
    (person,) = run([li(birth_year=1991)], index(record()))
    assert person.birth_year == 1991


def test_a_joined_player_merges_with_the_fetched_fide_profile():
    fide_profile = RawProfile(platform="fide", handle="1503014",
                              display_name="Magnus Carlsen", birth_year=1990)
    persons = run([li(), fide_profile], index(record()))
    assert len(persons) == 1
    assert {p.platform for p in persons[0].profiles} == {"lichess", "fide"}


def test_no_join_happens_without_an_index():
    persons = resolve([li()], github_client=NoGitHub(), github_for=0)
    assert persons[0].birth_year is None


def test_the_fide_link_is_stored_when_joined():
    (person,) = run([li()], index(record()))
    assert person.links["fide"] == "https://ratings.fide.com/profile/1503014"

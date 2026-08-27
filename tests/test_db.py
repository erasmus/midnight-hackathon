from core.db import Database
from core.schema import Person, RawProfile, Scores


def raw(handle="tourist", rating=3800, fetched_at="2026-08-28T00:00:00Z"):
    return RawProfile(
        platform="codeforces", handle=handle, rating=rating, fetched_at=fetched_at
    )


def test_reinserting_the_same_raw_profile_does_not_duplicate(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    db.upsert_raw_profiles([raw(), raw()])
    db.upsert_raw_profiles([raw()])
    assert len(db.all_raw_profiles()) == 1


def test_raw_profile_upsert_overwrites_with_newer_data(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    db.upsert_raw_profiles([raw(rating=3800)])
    db.upsert_raw_profiles([raw(rating=3900)])
    (stored,) = db.all_raw_profiles()
    assert stored.rating == 3900


def test_raw_profiles_round_trip_through_the_database(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    profile = raw()
    db.upsert_raw_profiles([profile])
    assert db.all_raw_profiles() == [profile]


def test_fetched_at_is_queryable_without_decoding_the_blob(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    db.upsert_raw_profiles([raw(fetched_at="2026-08-28T00:00:00Z")])
    rows = db.connection.execute(
        "SELECT platform, handle, fetched_at FROM raw_profiles"
    ).fetchall()
    assert rows == [("codeforces", "tourist", "2026-08-28T00:00:00Z")]


def test_reinserting_the_same_person_does_not_duplicate(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    person = Person(id="codeforces:tourist", display_name="tourist", profiles=[raw()])
    db.upsert_persons([person])
    db.upsert_persons([person])
    assert db.all_persons() == [person]


def test_scores_are_stored_per_person(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    db.upsert_scores([Scores(person_id="codeforces:tourist", composite=72.5)])
    db.upsert_scores([Scores(person_id="codeforces:tourist", composite=80.0)])
    (stored,) = db.all_scores()
    assert stored.composite == 80.0


def test_database_creates_its_file_and_tables(tmp_path):
    path = tmp_path / "db.sqlite"
    Database(path)
    assert path.exists()

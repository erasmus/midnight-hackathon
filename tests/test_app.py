import json
import threading
import urllib.request
from http.client import HTTPConnection

import pytest

from app import Explorer, build_server
from core.db import Database
from core.schema import Person, RawProfile, Scores


@pytest.fixture
def db_path(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    people = [
        Person(id="codeforces:ada", display_name="Ada Lovelace", birth_year=1990,
               country="GB", links={"linkedin": "https://l/in/ada"}, evidence=["ev"],
               profiles=[RawProfile(platform="codeforces", handle="ada",
                                    rank_pct=99.9, rating=3400)]),
        Person(id="lichess:kid", display_name="A Kid", birth_year=2015,
               links={"linkedin": "https://l/in/kid"}, evidence=["ev"],
               profiles=[RawProfile(platform="lichess", handle="kid", rating=2900)]),
    ]
    db.upsert_persons(people)
    db.close()
    return tmp_path / "db.sqlite"


@pytest.fixture
def explorer(db_path):
    return Explorer(db_path)


@pytest.fixture
def server(db_path):
    httpd = build_server(db_path, port=0)
    # Short poll interval: shutdown() otherwise blocks for the 0.5s default on
    # every test, which dominates the suite runtime.
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.02),
                              daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def get(server, path):
    conn = HTTPConnection("127.0.0.1", server.server_address[1])
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    conn.close()
    return response.status, body


def get_json(server, path):
    status, body = get(server, path)
    return status, json.loads(body)


# -- Explorer (no server needed) -------------------------------------------

def test_the_explorer_loads_people_from_the_database(explorer):
    assert len(explorer.persons) == 2


def test_scoring_returns_a_row_per_person(explorer):
    assert len(explorer.score()["rows"]) == 2


def test_rows_carry_the_scores(explorer):
    row = explorer.score()["rows"][0]
    assert "composite" in row and "outlierness" in row


def test_the_minor_is_excluded_by_default(explorer):
    rows = {r["person_id"]: r for r in explorer.score()["rows"]}
    assert rows["lichess:kid"]["excluded"] is True


def test_exclusion_reasons_are_returned(explorer):
    rows = {r["person_id"]: r for r in explorer.score()["rows"]}
    assert rows["lichess:kid"]["exclusion_reasons"]


def test_survivors_are_counted(explorer):
    summary = explorer.score()
    assert summary["total"] == 2 and summary["passed"] == 1


def test_lowering_the_age_floor_admits_the_minor(explorer):
    rows = {r["person_id"]: r for r in explorer.score(min_age=5)["rows"]}
    assert rows["lichess:kid"]["excluded"] is False


def test_custom_weights_change_the_composite(explorer):
    default = explorer.score()["rows"][0]["composite"]
    shifted = explorer.score(w_out=0.0, w_traj=0.0, w_addr=1.0)["rows"][0]["composite"]
    assert default != shifted


def test_rows_are_ranked_best_first(explorer):
    rows = explorer.score()["rows"]
    assert rows[0]["excluded"] is False


def test_the_explorer_uses_the_same_scoring_as_the_pipeline(explorer):
    from core.score import score_person
    row = next(r for r in explorer.score()["rows"] if r["person_id"] == "codeforces:ada")
    person = next(p for p in explorer.persons if p.id == "codeforces:ada")
    assert row["composite"] == score_person(person).composite


# -- HTTP ------------------------------------------------------------------

def test_the_index_page_is_served(server):
    status, body = get(server, "/")
    assert status == 200 and "<!doctype html>" in body.lower()


def test_the_page_is_self_contained(server):
    _, body = get(server, "/")
    assert "<script src=" not in body and 'link rel="stylesheet"' not in body


def test_the_page_supplies_its_own_favicon(server):
    # Otherwise every load logs a 404, which reads as an error during a demo.
    _, body = get(server, "/")
    assert 'rel="icon"' in body and "data:image/svg+xml" in body


def test_the_page_makes_no_external_requests(server):
    _, body = get(server, "/")
    external = [x for x in body.split('"') if x.startswith("http")
                and not x.startswith("http://www.w3.org")]
    assert external == []


def test_the_score_endpoint_returns_json(server):
    status, payload = get_json(server, "/api/score")
    assert status == 200 and "rows" in payload


def test_the_score_endpoint_accepts_parameters(server):
    _, payload = get_json(server, "/api/score?min_age=5")
    rows = {r["person_id"]: r for r in payload["rows"]}
    assert rows["lichess:kid"]["excluded"] is False


def test_invalid_parameters_do_not_crash_the_server(server):
    status, _ = get_json(server, "/api/score?min_age=banana&w_out=zzz")
    assert status == 200


def test_a_dossier_is_served_for_a_known_person(server):
    status, body = get(server, "/api/dossier/codeforces:ada")
    assert status == 200 and "Ada Lovelace" in body


def test_an_unknown_person_yields_404(server):
    status, _ = get(server, "/api/dossier/nobody:here")
    assert status == 404


def test_an_unknown_path_yields_404(server):
    status, _ = get(server, "/no/such/thing")
    assert status == 404


def test_the_server_binds_loopback_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_a_path_traversal_attempt_is_refused(server):
    status, _ = get(server, "/api/dossier/../../etc/passwd")
    assert status == 404

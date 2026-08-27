from pathlib import Path
import csv
import subprocess
import sys

from core.outputs import survivors, write_outputs
from core.schema import Person, RawProfile, Scores
from core.sparkline import sparkline_svg
from dossier import DRAFT_LABEL, render_dossier, write_dossier

REPO = Path(__file__).resolve().parent.parent


def _person(**kwargs):
    history = kwargs.pop("history", [{"date": "2024-01-01", "rating": 2400}, {"date": "2025-01-01", "rating": 2600}])
    extra_links = kwargs.pop("profile_links", ["https://github.com/alice"])
    raw = RawProfile(
        platform="codeforces",
        handle="alice",
        display_name="Alice Example",
        url="https://codeforces.com/profile/alice",
        rating=2600,
        rank_pct=99.5,
        rating_history=history,
        profile_links=extra_links,
        country="CH",
        birth_year=1999,
    )
    defaults = dict(
        id="codeforces:alice",
        display_name="Alice Example",
        country="CH",
        profiles=[raw],
        links={"github": "https://github.com/alice"},
        evidence=["Codeforces organization field lists github.com/alice"],
    )
    defaults.update(kwargs)
    return Person(**defaults)


def _score(person_id="codeforces:alice", **kwargs):
    defaults = dict(
        person_id=person_id,
        outlierness=90,
        trajectory=80,
        addressability=65,
        composite=81.0,
        flags=[],
    )
    defaults.update(kwargs)
    return Scores(**defaults)


def test_shortlist_csv_is_spreadsheet_friendly(tmp_path):
    paths = write_outputs([_person()], [_score()], tmp_path)
    csv_path = tmp_path / "shortlist.csv"
    assert csv_path in paths
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["name"] == "Alice Example"
    assert "codeforces" in rows[0]["domains"]
    assert ";" in rows[0]["evidence"] or rows[0]["evidence"]
    assert "{" not in rows[0]["evidence"]
    assert "github.com/alice" in rows[0]["links"]


def test_already_founder_never_reaches_the_shortlist(tmp_path):
    founder = _person(id="codeforces:ceo", display_name="Already Founded")
    founder.profiles[0].handle = "ceo"
    write_outputs(
        [_person(), founder],
        [
            _score(),
            _score(person_id="codeforces:ceo", flags=["already_founder"], composite=99),
        ],
        tmp_path,
    )
    with (tmp_path / "shortlist.csv").open(newline="", encoding="utf-8") as handle:
        names = [row["name"] for row in csv.DictReader(handle)]
    assert names == ["Alice Example"]


def test_shortlist_caps_at_twenty(tmp_path):
    persons = []
    scores = []
    for i in range(25):
        p = _person(id=f"p:{i}", display_name=f"P{i}", evidence=["e"], links={"github": f"https://github.com/p{i}"})
        persons.append(p)
        scores.append(_score(person_id=f"p:{i}", composite=float(i)))
    write_outputs(persons, scores, tmp_path)
    with (tmp_path / "shortlist.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 20
    assert rows[0]["name"] == "P24"


def test_dossier_html_is_self_contained_and_has_no_send():
    html = render_dossier(_person(), _score())
    assert "Alice Example" in html
    assert DRAFT_LABEL in html
    assert "mailto:" not in html.lower()
    assert "<form" not in html.lower()
    assert "send button" in html.lower() or "no send" in html.lower()
    assert "github.com/alice" in html
    assert "Codeforces organization field lists github.com/alice" in html
    assert "<svg" in html


def test_dossier_reads_evidence_not_just_the_links_dict():
    person = _person()
    person.profiles[0].profile_links = [
        "https://alice.dev",
        "https://notes.alice.dev",
        "https://github.com/alice",
    ]
    html = render_dossier(person, _score())
    assert "https://alice.dev" in html
    assert "https://notes.alice.dev" in html
    assert "alice.dev — " in html


def test_sparkline_degrades_without_history():
    person = _person(history=[])
    html = render_dossier(person, _score())
    assert "No rating history" in html
    assert sparkline_svg([]) is None


def test_names_are_html_escaped():
    raw = RawProfile(platform="x", handle="h", display_name="<script>", url=None)
    person = Person(id="x:h", display_name="<b>evil</b>", profiles=[raw])
    html = render_dossier(person, _score("x:h"))
    assert "<b>evil</b>" not in html
    assert "&lt;b&gt;evil&lt;/b&gt;" in html


def test_write_dossier_and_cli(tmp_path):
    from core.db import Database

    person = _person()
    score = _score()
    db_path = tmp_path / "db.sqlite"
    with Database(db_path) as db:
        db.upsert_persons([person])
        db.upsert_scores([score])
    path = write_dossier(person, score, tmp_path)
    assert path.exists()
    proc = subprocess.run(
        [sys.executable, "dossier.py", person.id, "--db", str(db_path), "--out", str(tmp_path / "cli")],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert Path(proc.stdout.strip()).exists()


def test_survivors_rank_none_composite_last():
    a = _person(id="a")
    b = _person(id="b")
    pairs = survivors(
        [a, b],
        [_score("a", composite=None), _score("b", composite=10)],
    )
    assert [p.id for p, _ in pairs] == ["b", "a"]

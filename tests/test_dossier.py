import pytest

from dossier import DRAFT_LABEL, outreach_angle, render_dossier, why_now, write_dossier
from core.schema import Person, RawProfile, Scores


def prof(platform="codeforces", rating=3400, rank_pct=99.99, hist=None, raw=None, **kw):
    return RawProfile(platform=platform, handle="ada", rating=rating, rank_pct=rank_pct,
                      url=f"https://{platform}.com/ada", rating_history=hist or [],
                      raw=raw or {}, **kw)


def person(**kw):
    kw.setdefault("id", "codeforces:ada")
    kw.setdefault("display_name", "Ada Lovelace")
    kw.setdefault("profiles", [prof()])
    kw.setdefault("country", "GB")
    links = kw.get("links")
    if links and not kw.get("evidence"):
        kw["evidence"] = [f"codeforces profile ada lists {u}" for u in links.values()]
    return Person(**kw)


def scores(**kw):
    kw.setdefault("person_id", "codeforces:ada")
    kw.setdefault("outlierness", 99.9)
    kw.setdefault("trajectory", 72.0)
    kw.setdefault("addressability", 45)
    kw.setdefault("composite", 79.0)
    return Scores(**kw)


def html(**kw):
    return render_dossier(person(**kw.pop("person_kw", {})), scores(**kw.pop("scores_kw", {})))


# -- structure -------------------------------------------------------------

def test_a_complete_html_document_is_produced():
    out = html()
    assert out.lstrip().startswith("<!doctype html>")
    assert "</html>" in out


def test_the_name_appears_in_the_header():
    assert "Ada Lovelace" in html()


def test_the_country_appears():
    assert "GB" in html()


def test_the_scores_are_shown():
    out = html()
    # Trailing zeros are trimmed for display: 79.0 renders as "79".
    assert "99.9" in out and "79" in out


def test_each_platform_gets_an_achievement_block():
    out = render_dossier(
        person(profiles=[prof("codeforces"), prof("lichess", rating=2900)]), scores()
    )
    assert "codeforces" in out and "lichess" in out


def test_achievement_blocks_carry_verifiable_links():
    assert "https://codeforces.com/ada" in html()


def test_the_document_is_self_contained():
    out = html()
    assert "<script src=" not in out
    assert "<link rel=\"stylesheet\"" not in out


def test_a_sparkline_renders_when_there_is_history():
    hist = [{"date": "2024-01-01", "rating": 2400}, {"date": "2024-06-01", "rating": 2700}]
    out = render_dossier(person(profiles=[prof(hist=hist)]), scores())
    assert "<svg" in out


def test_the_dossier_degrades_gracefully_without_history():
    out = html()
    assert "<svg" not in out
    assert "</html>" in out


# -- consent and provenance ------------------------------------------------

def test_every_link_shown_has_a_provenance_line():
    p = person(links={"github": "https://github.com/ada"})
    out = render_dossier(p, scores())
    assert "https://github.com/ada" in out
    assert "codeforces profile ada lists https://github.com/ada" in out


def test_the_evidence_appendix_is_present():
    out = render_dossier(person(links={"github": "https://github.com/ada"}), scores())
    assert "evidence" in out.lower()


def test_weak_matches_are_never_shown():
    p = person(weak_matches=["github.com/ada shares the handle but no corroboration"])
    out = render_dossier(p, scores())
    assert "no corroboration" not in out


def test_exclusion_reasons_are_shown_when_present():
    out = render_dossier(person(), scores(excluded=True, exclusion_reasons=["under 18"]))
    assert "under 18" in out


def test_flags_are_rendered():
    out = render_dossier(person(), scores(flags=["single_source"]))
    assert "single_source" in out


# -- outreach draft --------------------------------------------------------

def test_the_outreach_angle_is_labelled_a_draft():
    assert DRAFT_LABEL in html()


def test_the_draft_label_says_edit_before_sending():
    assert "edit before sending" in DRAFT_LABEL.lower()


def test_the_outreach_angle_references_their_actual_work():
    angle = outreach_angle(person(), scores())
    assert "codeforces" in angle.lower()


def test_the_outreach_angle_is_two_sentences():
    angle = outreach_angle(person(), scores())
    assert 1 <= angle.count(".") <= 3


def test_no_send_capability_exists_anywhere():
    import dossier as module
    source = open(module.__file__, encoding="utf-8").read().lower()
    for forbidden in ("smtplib", "sendmail", "def send", "requests.post", "mailto:"):
        assert forbidden not in source


def test_why_now_is_a_single_line():
    line = why_now(person(), scores())
    assert "\n" not in line and line


# -- file output -----------------------------------------------------------

def test_a_self_contained_file_is_written(tmp_path):
    path = write_dossier(person(), scores(), tmp_path)
    assert path.exists() and path.suffix == ".html"
    assert "Ada Lovelace" in path.read_text(encoding="utf-8")


def test_the_filename_is_derived_from_the_person_id(tmp_path):
    path = write_dossier(person(), scores(), tmp_path)
    assert "codeforces" in path.name and "ada" in path.name


def test_unicode_survives_the_file_write(tmp_path):
    path = write_dossier(person(display_name="Paweł Teclaf"), scores(), tmp_path)
    assert "Paweł Teclaf" in path.read_text(encoding="utf-8")


def test_html_special_characters_in_a_name_are_escaped(tmp_path):
    out = render_dossier(person(display_name="<script>alert(1)</script>"), scores())
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out

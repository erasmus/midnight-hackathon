import pytest

from core.github_match import GITHUB_API, Match, check_handle_reuse
from core.schema import RawProfile


class FakeClient:
    def __init__(self, users=None, fail=False):
        self.users = users or {}
        self.fail = fail
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        if self.fail:
            raise RuntimeError("404")
        handle = url.rstrip("/").split("/")[-1]
        if handle not in self.users:
            raise RuntimeError("404 Not Found")
        return self.users[handle]


def gh(login, name=None, bio=None, blog=None, company=None):
    return {"login": login, "name": name, "bio": bio, "blog": blog,
            "company": company, "html_url": f"https://github.com/{login}"}


def profile(handle="tourist", display_name="Gennady Korotkevich", platform="codeforces", **kw):
    return RawProfile(platform=platform, handle=handle, display_name=display_name, **kw)


def test_no_github_account_means_no_match():
    match = check_handle_reuse(profile(), client=FakeClient({}))
    assert match is None


def test_matching_display_name_corroborates():
    users = {"tourist": gh("tourist", name="Gennady Korotkevich")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert match.accepted is True


def test_a_bare_handle_collision_is_a_weak_match():
    users = {"tourist": gh("tourist")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert match.accepted is False
    assert match.kind == "weak_match"


def test_a_weak_match_carries_no_usable_link():
    users = {"tourist": gh("tourist")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert match.link is None


def test_an_accepted_match_carries_a_link():
    users = {"tourist": gh("tourist", name="Gennady Korotkevich")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert match.link == "https://github.com/tourist"


def test_bio_mentioning_the_platform_corroborates():
    users = {"tourist": gh("tourist", bio="Codeforces grandmaster, competitive programmer")}
    match = check_handle_reuse(profile(display_name="Someone Else"), client=FakeClient(users))
    assert match.accepted is True


def test_a_github_profile_linking_back_corroborates():
    users = {"tourist": gh("tourist", blog="https://codeforces.com/profile/tourist")}
    match = check_handle_reuse(profile(display_name="Someone Else"), client=FakeClient(users))
    assert match.accepted is True


def test_a_link_back_in_the_company_field_corroborates():
    users = {"tourist": gh("tourist", company="codeforces.com/profile/tourist")}
    match = check_handle_reuse(profile(display_name="Someone Else"), client=FakeClient(users))
    assert match.accepted is True


def test_an_unrelated_name_and_bio_stays_weak():
    users = {"tourist": gh("tourist", name="Tourist Agency", bio="we sell holidays")}
    match = check_handle_reuse(profile(display_name="Gennady Korotkevich"), client=FakeClient(users))
    assert match.accepted is False


def test_name_comparison_ignores_case_and_spacing():
    users = {"tourist": gh("tourist", name="  gennady   KOROTKEVICH ")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert match.accepted is True


def test_a_display_name_equal_to_the_handle_does_not_corroborate():
    # The handle matching itself is the collision, not evidence about it.
    users = {"tourist": gh("tourist", name="tourist")}
    match = check_handle_reuse(profile(display_name="tourist"), client=FakeClient(users))
    assert match.accepted is False


def test_a_single_token_name_does_not_corroborate():
    users = {"tourist": gh("tourist", name="Gennady")}
    match = check_handle_reuse(profile(display_name="Gennady"), client=FakeClient(users))
    assert match.accepted is False


def test_accepted_match_evidence_names_the_corroborating_signal():
    users = {"tourist": gh("tourist", name="Gennady Korotkevich")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert "name" in match.evidence.lower()
    assert "Gennady Korotkevich" in match.evidence


def test_bio_match_evidence_quotes_the_bio():
    users = {"tourist": gh("tourist", bio="Codeforces grandmaster")}
    match = check_handle_reuse(profile(display_name="X Y"), client=FakeClient(users))
    assert "Codeforces grandmaster" in match.evidence


def test_weak_match_evidence_says_why_it_was_refused():
    users = {"tourist": gh("tourist")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert "no corroborat" in match.evidence.lower()


def test_the_github_api_is_queried_for_the_platform_handle():
    c = FakeClient({"tourist": gh("tourist")})
    check_handle_reuse(profile(), client=c)
    assert c.calls == [f"{GITHUB_API}/users/tourist"]


def test_an_api_failure_yields_no_match_rather_than_an_error():
    match = check_handle_reuse(profile(), client=FakeClient(fail=True))
    assert match is None


def test_a_profile_without_a_handle_is_not_queried():
    c = FakeClient({})
    assert check_handle_reuse(RawProfile(platform="x", handle=""), client=c) is None
    assert c.calls == []


def test_multiple_corroborating_signals_are_all_reported():
    users = {"tourist": gh("tourist", name="Gennady Korotkevich", bio="Codeforces GM")}
    match = check_handle_reuse(profile(), client=FakeClient(users))
    assert len(match.signals) == 2

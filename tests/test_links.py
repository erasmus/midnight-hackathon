from core.links import Link, classify, extract_links
from core.schema import RawProfile


def profile(links, platform="lichess", link_sources=None, display_name="Alice"):
    return RawProfile(
        platform=platform,
        handle="alice",
        display_name=display_name,
        profile_links=links,
        raw={"link_sources": link_sources} if link_sources else {},
    )


def kinds(links):
    return [l.kind for l in links]


def test_github_profile_url_is_classified_as_github():
    assert classify("https://github.com/alice")[0] == "github"


def test_github_handle_is_extracted():
    assert classify("https://github.com/alice")[1] == "alice"


def test_github_repo_url_yields_the_owner_handle():
    assert classify("https://github.com/alice/project") == ("github", "alice")


def test_github_reserved_paths_are_not_mistaken_for_handles():
    kind, handle = classify("https://github.com/orgs/some-org")
    assert handle is None


def test_linkedin_profile_is_classified():
    assert classify("https://linkedin.com/in/alice-adams")[0] == "linkedin"


def test_linkedin_company_page_is_not_a_person():
    assert classify("https://linkedin.com/company/acme")[0] != "linkedin"


def test_twitter_is_classified():
    assert classify("https://twitter.com/alice") == ("twitter", "alice")


def test_x_dot_com_is_classified_as_twitter():
    assert classify("https://x.com/alice") == ("twitter", "alice")


def test_unrecognised_domain_becomes_a_personal_site_candidate():
    assert classify("https://alice.dev")[0] == "personal_site"


def test_unclassifiable_urls_are_kept_not_dropped():
    links = extract_links(profile(["https://some-obscure-host.example/~alice"]))
    assert len(links) == 1
    assert links[0].kind == "personal_site"


def test_www_and_trailing_slash_do_not_change_classification():
    assert classify("https://www.github.com/alice/") == ("github", "alice")


def test_uppercase_host_is_handled():
    assert classify("HTTPS://GitHub.com/Alice")[0] == "github"


def test_a_url_without_a_scheme_is_still_classified():
    assert classify("github.com/alice") == ("github", "alice")


def test_every_extracted_link_carries_evidence():
    links = extract_links(profile(["https://github.com/alice"]))
    assert all(l.evidence for l in links)


def test_evidence_names_the_source_platform():
    (link,) = extract_links(profile(["https://github.com/alice"], platform="codeforces"))
    assert "codeforces" in link.evidence.lower()


def test_evidence_names_the_source_field_when_the_adapter_recorded_it():
    (link,) = extract_links(
        profile(["https://github.com/alice"], link_sources={"https://github.com/alice": "bio"})
    )
    assert "bio" in link.evidence


def test_evidence_quotes_the_url():
    (link,) = extract_links(profile(["https://github.com/alice"]))
    assert "https://github.com/alice" in link.evidence


def test_evidence_falls_back_to_a_generic_field_when_unrecorded():
    (link,) = extract_links(profile(["https://github.com/alice"]))
    assert link.evidence


def test_link_records_where_it_came_from():
    (link,) = extract_links(profile(["https://github.com/alice"], platform="lichess"))
    assert link.source_platform == "lichess"
    assert link.source_handle == "alice"


def test_all_of_a_profiles_links_flow_through_the_classifier():
    links = extract_links(
        profile([
            "https://github.com/alice",
            "https://linkedin.com/in/alice",
            "https://x.com/alice",
            "https://alice.dev",
        ])
    )
    assert kinds(links) == ["github", "linkedin", "twitter", "personal_site"]


def test_duplicate_urls_are_extracted_once():
    links = extract_links(profile(["https://github.com/alice", "https://github.com/alice/"]))
    assert len(links) == 1


def test_a_profile_with_no_links_yields_nothing():
    assert extract_links(profile([])) == []


def test_empty_and_malformed_urls_are_ignored():
    assert extract_links(profile(["", "   ", "not a url"])) == []


def test_mailto_links_are_ignored():
    assert extract_links(profile(["mailto:alice@example.com"])) == []


def test_links_are_hashable_for_dedupe_across_profiles():
    (link,) = extract_links(profile(["https://github.com/alice"]))
    assert isinstance(hash(link), int)

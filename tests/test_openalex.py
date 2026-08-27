from adapters import openalex
from core import enrich
from core.schema import RawProfile


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        for fragment, payload in self.payloads.items():
            if fragment in url:
                return payload
        raise AssertionError(f"unexpected URL {url}")


def author(oid, name, cited, works, years, **extra):
    counts = [{"year": y, "works_count": 1, "cited_by_count": 1} for y in years]
    inst = extra.pop("institution", None)
    country = extra.pop("country_code", "US")
    orcid = extra.pop("orcid", None)
    return {
        "id": f"https://openalex.org/{oid}",
        "display_name": name,
        "cited_by_count": cited,
        "works_count": works,
        "counts_by_year": counts,
        "orcid": orcid,
        "ids": {"orcid": orcid} if orcid else {},
        "last_known_institutions": [{"display_name": inst, "country_code": country}] if inst else [],
        **extra,
    }


def test_keeps_short_career_high_citation_authors():
    this_year = openalex._year_now()
    client = FakeClient(
        {
            "authors?": {
                "results": [
                    author("A1", "Young Star", 400, 12, [this_year - 2, this_year], institution="KAIST"),
                    author("A2", "Old Guard", 9000, 20, [1990, 1991, this_year], institution="MIT"),
                ]
            }
        }
    )
    profiles = openalex.fetch_top(50, client=client)
    assert [p.handle for p in profiles] == ["A1"]
    assert profiles[0].display_name == "Young Star"
    assert profiles[0].raw["institution"] == "KAIST"
    assert profiles[0].raw["metric_name"] == "citation_velocity"
    assert profiles[0].rating == 400 / 2
    assert isinstance(profiles[0], RawProfile)


def test_orcid_is_captured_as_a_self_link():
    this_year = openalex._year_now()
    client = FakeClient(
        {
            "authors?": {
                "results": [
                    author(
                        "A1",
                        "Noura",
                        200,
                        10,
                        [this_year - 1],
                        orcid="https://orcid.org/0000-0002-0000-0001",
                    )
                ]
            }
        }
    )
    profiles = openalex.fetch_top(10, client=client)
    assert "https://orcid.org/0000-0002-0000-0001" in profiles[0].profile_links


def test_lookup_papers_returns_titles_or_empty():
    client = FakeClient(
        {
            "works?": {
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "Cheap, Sharp",
                        "publication_year": 2025,
                        "cited_by_count": 12,
                        "ids": {"doi": "https://doi.org/10.0/xyz"},
                        "primary_location": {"landing_page_url": "https://github.com/arao/eval"},
                        "authorships": [{"author": {"display_name": "Ananya Rao"}}],
                    }
                ]
            }
        }
    )
    papers = openalex.lookup_papers("Ananya Rao", client=client)
    assert papers[0]["title"] == "Cheap, Sharp"
    assert openalex.github_urls_from_papers(papers) == ["https://github.com/arao/eval"]
    assert enrich.lookup_papers("Ananya Rao", client=client)[0]["title"] == "Cheap, Sharp"


def test_lookup_papers_empty_on_miss():
    client = FakeClient({"works?": {"results": []}})
    assert openalex.lookup_papers("Nobody", client=client) == []


def test_caps_results():
    this_year = openalex._year_now()
    results = [
        author(f"A{i}", f"N{i}", 1000 - i, 10, [this_year - 1]) for i in range(30)
    ]
    client = FakeClient({"authors?": {"results": results}})
    assert len(openalex.fetch_top(5, client=client)) == 5


def test_adapter_exposes_the_pipeline_interface():
    assert callable(openalex.fetch_top)
    assert callable(openalex.lookup_papers)
    assert openalex.name == "openalex"

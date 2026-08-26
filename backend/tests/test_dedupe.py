"""Listing dedupe: the same role reposted as multiple reqs collapses to one (the first/best),
while distinct titles (e.g. different location baked in) survive."""

from types import SimpleNamespace as NS

from app.repository import _dedupe_listings


def _j(co, title):
    return NS(company_name=co, title=title)


def test_collapses_same_company_and_title():
    rows = [_j("Datadog", "Strategic Account Executive")] * 8 + [_j("Toast", "Data Analyst")]
    out = _dedupe_listings(rows)
    assert len(out) == 2


def test_keeps_first_best_ranked_copy():
    rows = [_j("Acme", "Analyst"), _j("Acme", "Analyst"), _j("Acme", "Senior Analyst")]
    out = _dedupe_listings(rows)
    assert [r.title for r in out] == ["Analyst", "Senior Analyst"]


def test_distinct_locations_in_title_survive():
    rows = [_j("Toast", "AE, Retail - Fort Worth"), _j("Toast", "AE, Retail - Columbus")]
    assert len(_dedupe_listings(rows)) == 2


def test_case_and_whitespace_insensitive():
    rows = [_j("Acme", "Data  Analyst"), _j("acme", "data analyst")]
    assert len(_dedupe_listings(rows)) == 1

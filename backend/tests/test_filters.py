"""Triage filters (spec section 41): exclude-keywords, employment type, entry-friendly."""

from app.db import SessionLocal, init_db
from app.models import Job
from app.repository import SQLiteJobRepository

init_db()
repo = SQLiteJobRepository()
IDS = ["zzf:1", "zzf:2", "zzf:3"]


def _cleanup():
    with SessionLocal() as s:
        for i in IDS:
            j = s.get(Job, i)
            if j:
                s.delete(j)
        s.commit()


def _mk(s, jid, title, emp=None, seniority="mid", years=None, desc=""):
    s.add(Job(id=jid, source_type="zz", company_token="x", source_job_id=jid,
              title=title, company_name="Acme", employment_type=emp, seniority=seniority,
              required_years_max=years, description_text=desc, relevance_score=90,
              priority_score=500, freshness="ACTIVE", status="NEW"))


def setup_function(_):
    _cleanup()
    with SessionLocal() as s:
        _mk(s, "zzf:1", "ZZFILTER Dev A", emp="full_time", seniority="mid", years=2, desc="great role")
        _mk(s, "zzf:2", "ZZFILTER Dev B", emp="contract", seniority="senior", years=5,
            desc="requires active clearance")
        _mk(s, "zzf:3", "ZZFILTER Dev C", emp="full_time", seniority="junior", desc="entry level")
        s.commit()


def teardown_function(_):
    _cleanup()


def _ids(**kw):
    return {j.id for j in repo.list_jobs(query="zzfilter", min_score=0, limit=50, **kw)}


def test_exclude_keyword_hides_matches():
    assert _ids(exclude=["clearance"]) == {"zzf:1", "zzf:3"}      # B has "clearance"


def test_employment_type_filter():
    assert _ids(employment_type="contract") == {"zzf:2"}
    assert _ids(employment_type="full_time") == {"zzf:1", "zzf:3"}


def test_entry_only_drops_senior_and_high_years():
    assert _ids(entry_only=True) == {"zzf:1", "zzf:3"}            # B is senior + 5 yrs


def test_no_filter_returns_all_three():
    assert _ids() == {"zzf:1", "zzf:2", "zzf:3"}

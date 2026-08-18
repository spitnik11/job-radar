"""Freshness / stale pruning (spec section 28) + new-job counting for the refresh banner."""

from datetime import datetime

from app.db import SessionLocal, init_db
from app.models import Job
from app.repository import SQLiteJobRepository

init_db()
repo = SQLiteJobRepository()
IDS = ["fr:acme:1", "fr:acme:2", "fr:beta:1"]


def _cleanup():
    with SessionLocal() as s:
        for i in IDS:
            j = s.get(Job, i)
            if j:
                s.delete(j)
        s.commit()


def _mk(s, jid, token, last_seen, first_seen=None, relevance=90, priority=500):
    s.add(Job(id=jid, source_type="fr", company_token=token, source_job_id=jid,
              title="Dev", company_name="X", last_seen_at=last_seen,
              first_seen_at=first_seen or last_seen, relevance_score=relevance,
              priority_score=priority, freshness="ACTIVE", status="NEW"))


def setup_function(_):
    _cleanup()


def teardown_function(_):
    _cleanup()


def test_mark_stale_expires_only_unseen_on_fetched_boards():
    with SessionLocal() as s:
        _mk(s, "fr:acme:1", "acme", datetime(2026, 1, 1, 0, 0))     # not seen this run
        _mk(s, "fr:acme:2", "acme", datetime(2026, 1, 2, 0, 0))     # seen after start
        _mk(s, "fr:beta:1", "beta", datetime(2026, 1, 1, 0, 0))     # board NOT fetched
        s.commit()
    start = datetime(2026, 1, 1, 12, 0)
    n = repo.mark_stale({("fr", "acme")}, start)
    with SessionLocal() as s:
        assert s.get(Job, "fr:acme:1").freshness == "EXPIRED"       # closed
        assert s.get(Job, "fr:acme:2").freshness == "ACTIVE"        # re-seen
        assert s.get(Job, "fr:beta:1").freshness == "ACTIVE"        # its board failed/absent
    assert n == 1


def test_count_new_counts_recent_arrivals():
    # cutoff in the future so real seed jobs (first-seen ~now) don't count — isolates the two below
    cutoff = datetime(2027, 1, 1, 12, 0)
    with SessionLocal() as s:
        _mk(s, "fr:acme:1", "acme", datetime(2027, 1, 1, 13, 0))    # first seen after cutoff
        _mk(s, "fr:acme:2", "acme", datetime(2027, 1, 1, 10, 0))    # before cutoff
        s.commit()
    assert repo.count_new(cutoff, 65) == 1


def test_expired_hidden_from_default_feed():
    with SessionLocal() as s:
        _mk(s, "fr:acme:1", "acme", datetime(2026, 1, 1))
        _mk(s, "fr:acme:2", "acme", datetime(2026, 1, 1))
        s.commit()
    with SessionLocal() as s:
        s.get(Job, "fr:acme:1").freshness = "EXPIRED"
        s.commit()
    ids = [j.id for j in repo.list_jobs(min_score=0, limit=2000)]
    assert "fr:acme:1" not in ids and "fr:acme:2" in ids

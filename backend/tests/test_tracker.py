"""Application tracking (spec section 29): status changes auto-log events, notes merge in."""

from app.db import SessionLocal, init_db
from app.models import Job, JobEvent, JobNote
from app.repository import SQLiteJobRepository

init_db()
repo = SQLiteJobRepository()
JID = "test-tracker:x:1"


def _cleanup():
    with SessionLocal() as s:
        for M in (JobNote, JobEvent):
            for r in s.query(M).filter(M.job_id == JID).all():
                s.delete(r)
        j = s.get(Job, JID)
        if j:
            s.delete(j)
        s.commit()


def setup_function(_):
    _cleanup()
    with SessionLocal() as s:
        s.add(Job(id=JID, source_type="test", company_token="x", source_job_id="1",
                  title="Test", company_name="Acme", status="VIEWED"))
        s.commit()


def teardown_function(_):
    _cleanup()


def test_status_changes_log_events_newest_first():
    repo.set_status(JID, "SAVED")
    repo.set_status(JID, "APPLIED")
    acts = repo.list_activity(JID)
    assert [a["kind"] for a in acts].count("status") == 2
    assert acts[0]["text"].endswith("APPLIED")          # newest first


def test_viewed_transition_not_logged():
    repo.set_status(JID, "VIEWED")
    assert repo.list_activity(JID) == []


def test_note_merges_into_timeline():
    repo.set_status(JID, "APPLIED")
    repo.add_note(JID, "Recruiter emailed about a phone screen")
    acts = repo.list_activity(JID)
    assert len(acts) == 2
    assert any(a["kind"] == "note" and "Recruiter" in a["text"] for a in acts)


def test_add_note_to_missing_job_returns_none():
    assert repo.add_note("nope:x:0", "hi") is None

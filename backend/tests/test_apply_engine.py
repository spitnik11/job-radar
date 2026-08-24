"""Engine verification against local mock forms (no real employer touched). Each mock reproduces a
real edge case seen on live ATS forms; we assert the engine fills what it can and classifies every
blocker that would stop a submission. Requires Playwright's chromium; skipped if unavailable."""

from pathlib import Path

import pytest

from app.apply import engine
from app.apply_kit import ApplicationKit

MOCKS = Path(__file__).parent / "mocks"
pytestmark = pytest.mark.skipif(
    __import__("importlib").util.find_spec("playwright") is None, reason="playwright not installed")

KIT = ApplicationKit(
    full_name="Test User", email="test@example.com", phone="5555550123",
    city="Brandon", state="FL", gender="Male", authorized_us=True,
    start_date="As soon as possible", resume_path=str(MOCKS / "resume.txt"),
)


def _prep(name):
    url = (MOCKS / name).as_uri()
    return engine.prepare({"id": f"mock:{name}", "apply_url": url, "title": name, "company_name": "Mock"}, kit=KIT)


def test_clean_form_reaches_submission_ready():
    # exercises: React input needing keystrokes, invisible reCAPTCHA badge (must NOT block),
    # file upload, required select/radio/consent, the "when can you start" mapping.
    r = _prep("clean.html")
    assert r["status"] == "ready_to_submit", r["blockers"]
    assert r["blockers"] == []


def test_required_unanswered_question_blocks():
    r = _prep("required_q.html")
    assert r["status"] == "blocked"
    assert any("question" in b.lower() or "still empty" in b.lower() for b in r["blockers"])


def test_visible_captcha_challenge_blocks():
    r = _prep("captcha.html")
    assert r["status"] == "blocked"
    assert any("captcha" in b.lower() for b in r["blockers"])


def test_multistep_form_flagged():
    r = _prep("multistep.html")
    assert r["status"] == "blocked"
    assert any("multi-step" in b.lower() for b in r["blockers"])


def test_disabled_submit_flagged():
    r = _prep("disabled.html")
    assert r["status"] == "blocked"
    assert any("disabled" in b.lower() for b in r["blockers"])

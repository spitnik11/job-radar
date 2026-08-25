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


def test_rerender_wipe_recovered_by_reconcile():
    # attaching the résumé wipes an already-filled required field; the reconcile pass must re-fill it.
    r = _prep("rerender.html")
    assert r["status"] == "ready_to_submit", r["blockers"]


def test_async_resume_upload_detected_as_attached():
    # Ashby-style: upload clears input.files and shows a filename chip; must NOT read as still-empty.
    r = _prep("ashby_upload.html")
    assert r["status"] == "ready_to_submit", r["blockers"]


def test_custom_radio_fills_from_answer_library():
    from app.apply import engine as eng
    from app.apply_kit import ApplicationKit
    url = (MOCKS / "custom_radio.html").as_uri()
    kit = ApplicationKit(full_name="T", email="t@e.com", phone="5",
                         resume_path=str(MOCKS / "resume.txt"),
                         answer_library={"Which team are you applying to?": "Growth"})
    r = eng.prepare({"id": "m:cr", "apply_url": url, "title": "x", "company_name": "y"}, kit=kit)
    assert r["status"] == "ready_to_submit", r["blockers"]
    assert any(f["type"] == "radio" and f["option"] == "Growth" for f in r["filled"])


def test_ashby_custom_radios_labelled_required_and_filled():
    # Ashby-style: fieldset + `_required` heading + opacity:0 radios under labels. The group label must
    # be the QUESTION (not "Yes"), required must be detected, and the auth radios must fill to Yes.
    r = _prep("ashby_radio.html")
    assert r["status"] == "ready_to_submit", r["blockers"]
    radios = [f for f in r["filled"] if f["type"] == "radio"]
    assert len(radios) == 2
    assert all(f["option"] == "Yes" for f in radios)
    assert all("authoriz" in f["label"].lower() or "right to work" in f["label"].lower() for f in radios)


def test_combobox_selects_a_suggestion_not_raw_text():
    from app.apply import filler
    from playwright.sync_api import sync_playwright
    url = (MOCKS / "autocomplete.html").as_uri()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(); pg.goto(url, wait_until="domcontentloaded")
        try:
            filler._fill_text(pg, "#loc", "Brandon, FL")
            assert pg.eval_on_selector("#loc", "e=>e.value") == "Brandon, FL, USA"
        finally:
            b.close()

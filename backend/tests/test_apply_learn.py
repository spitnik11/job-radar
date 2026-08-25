"""Continuous-learning: read the user's manual answers off the form, and save custom answers /
corrections (not standard PII) into the answer library so the next run auto-fills them."""

from pathlib import Path

import pytest

from app.apply import assist
from app.apply_kit import ApplicationKit

MOCKS = Path(__file__).parent / "mocks"
pytestmark = pytest.mark.skipif(
    __import__("importlib").util.find_spec("playwright") is None, reason="playwright not installed")


def test_read_answers_reads_text_custom_and_buttongroup():
    from app.apply import filler
    from playwright.sync_api import sync_playwright
    url = (MOCKS / "learn.html").as_uri()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(); pg.goto(url, wait_until="domcontentloaded"); pg.wait_for_timeout(200)
        try:
            pg.fill("#nm", "Gabriel Pina"); pg.fill("#q1", "I love building AI agents."); pg.click("text=Remote")
            pg.wait_for_timeout(150)
            got = {a["label"]: a["value"] for a in filler.read_answers(pg)}
            assert got["What excites you about this role?"] == "I love building AI agents."
            assert got["Preferred work style?"] == "Remote"
        finally:
            b.close()


def test_learn_saves_custom_answers_skips_standard(monkeypatch):
    saved = {}
    monkeypatch.setattr(assist, "save_kit", lambda data: saved.update(data))
    final = [
        {"label": "Full Name", "value": "Gabriel Pina", "type": "text"},       # standard PII → skip
        {"label": "What excites you about this role?", "value": "AI agents", "type": "textarea"},  # custom → learn
        {"label": "Preferred work style?", "value": "Remote", "type": "buttons"},                  # custom → learn
    ]
    n = assist._learn(ApplicationKit(), final, set(), {"full name": "Gabriel Pina"})
    assert n == 2
    lib = saved["answer_library"]
    assert lib["What excites you about this role?"] == "AI agents"
    assert lib["Preferred work style?"] == "Remote"
    assert "Full Name" not in lib


def test_learn_captures_a_correction(monkeypatch):
    saved = {}
    monkeypatch.setattr(assist, "save_kit", lambda data: saved.update(data))
    # we auto-filled the essay one way; the user rewrote it → learn the correction
    final = [{"label": "Why this company?", "value": "Your mission resonates", "type": "textarea"}]
    n = assist._learn(ApplicationKit(), final, set(), {"why this company?": "generic filler"})
    assert n == 1 and saved["answer_library"]["Why this company?"] == "Your mission resonates"

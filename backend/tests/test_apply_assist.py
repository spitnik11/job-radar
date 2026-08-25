"""Confirmation detection: the counter only moves when a real submit produced the employer's
confirmation page. Verify the detector fires on a confirmation and stays quiet on the raw form."""

from pathlib import Path

import pytest

from app.apply import assist

MOCKS = Path(__file__).parent / "mocks"
pytestmark = pytest.mark.skipif(
    __import__("importlib").util.find_spec("playwright") is None, reason="playwright not installed")


def _on(name):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto((MOCKS / name).as_uri(), wait_until="domcontentloaded")
        try:
            return assist.confirmed(pg)
        finally:
            b.close()


def test_detects_confirmation_page():
    assert _on("confirmed.html") is True


def test_raw_form_is_not_a_confirmation():
    assert _on("clean.html") is False

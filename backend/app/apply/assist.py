"""Assisted review-and-submit. Opens a VISIBLE browser, fills the form from the kit, then hands it
to the user: they review every field and click Submit themselves. This module never clicks Submit —
it only watches the page and, when it sees the employer's confirmation, reports the application as
submitted so the counter moves on a *real* submit. The human is the one who applies, every time.

Runs the Playwright sync API in a background thread (one session), so the HTTP call that starts it
returns immediately and the browser stays interactive."""

from __future__ import annotations

import threading

from ..apply_kit import load_kit
from . import answers, filler, formreader, mapping

_CONFIRM = ("thank you", "application received", "we received your application", "successfully submitted",
            "your application has been", "thanks for applying", "application submitted",
            "we'll be in touch", "has been received", "successfully applied")

# job_id -> {status, reason}. status: opening | review | submitted | closed | error.
_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def _set(job_id, status, reason=None):
    with _lock:
        _sessions[job_id] = {"status": status, "reason": reason}


def status(job_id: str | None = None):
    with _lock:
        return dict(_sessions.get(job_id, {"status": "none"})) if job_id else dict(_sessions)


def confirmed(page) -> bool:
    try:
        if any(w in (page.url or "").lower() for w in ("confirm", "thank", "success", "submitted", "applied")):
            return True
        body = (page.inner_text("body")[:6000] or "").lower()
    except Exception:
        return False
    return any(h in body for h in _CONFIRM)


def start(job: dict, on_confirm) -> None:
    """Launch the assisted session in a background thread. on_confirm(job_id) is called once, only
    when the employer's confirmation page is detected (i.e. the user actually submitted)."""
    job_id = job["id"]
    _set(job_id, "opening")
    threading.Thread(target=_run, args=(job, on_confirm), daemon=True).start()


def _run(job: dict, on_confirm) -> None:
    job_id = job["id"]
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            # VISIBLE, real window the user drives. no_viewport lets the page size to the actual
            # window so it scrolls normally — a fixed viewport taller than the screen leaves the
            # Submit button off-screen and unreachable.
            browser = p.chromium.launch(headless=False, args=["--start-maximized"])
            ctx = browser.new_context(no_viewport=True)
            page = ctx.new_page()
            page.goto(job["apply_url"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            fields = formreader.read_form(page)
            if fields:
                kit = load_kit()
                plan = mapping.map_fields(kit, fields)
                jctx = {"title": job.get("title"), "company": job.get("company_name")}
                plan, _ = answers.resolve(kit, plan, jctx)
                filler.fill(page, plan)
            _set(job_id, "review", "Filled — review every field, then click Submit yourself.")
            # watch for the user's submission (never submit for them). ~12 min, or until they close it.
            for _ in range(360):
                page.wait_for_timeout(2000)
                try:
                    if confirmed(page):
                        _set(job_id, "submitted", "Confirmation detected — marked as applied.")
                        try:
                            on_confirm(job_id)
                        except Exception:
                            pass
                        page.wait_for_timeout(4000)
                        break
                    _ = page.title()                        # raises if the user closed the window
                except Exception:
                    _set(job_id, "closed", "Browser closed before a confirmation was seen.")
                    break
            else:
                _set(job_id, "closed", "Timed out waiting for submission.")
            try:
                browser.close()
            except Exception:
                pass
    except Exception as e:
        _set(job_id, "error", f"{type(e).__name__}: {str(e)[:160]}")

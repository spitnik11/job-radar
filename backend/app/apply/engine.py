"""Dry-run engine. Opens a job's apply page in a headless browser, reads the form, maps the kit,
screenshots the plan, and returns it. NEVER fills or submits anything (Phase A safety). Runs the
Playwright *sync* API, so call it from a threadpool (a plain `def` FastAPI route), not the loop."""

from __future__ import annotations

from ..apply_kit import load_kit
from ..config import DATA_DIR
from . import formreader, mapping

SHOTS_DIR = DATA_DIR / "apply_shots"


def shot_path(job_id: str):
    """Job ids contain ':' (e.g. greenhouse:gitlab:123) which is illegal in Windows filenames —
    slug it. Same function on write and read so the screenshot endpoint finds the file."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_id)
    return SHOTS_DIR / f"{safe}.png"
_BLOCK_HINTS = ("captcha", "recaptcha", "cf-challenge", "are you human", "sign in to apply",
                "log in to apply", "create an account")


def _blocker(page) -> str | None:
    url = (page.url or "").lower()
    if "login" in url or "signin" in url or "sign-in" in url:
        return "login required"
    try:
        if page.query_selector("iframe[src*='recaptcha'], iframe[title*='captcha'], .g-recaptcha"):
            return "CAPTCHA present"
        body = (page.inner_text("body")[:4000] or "").lower()
    except Exception:
        return None
    for h in _BLOCK_HINTS:
        if h in body:
            return "CAPTCHA present" if "captcha" in h or "human" in h else "login/account required"
    return None


def _reach_form(page):
    """Some boards show the posting first with an 'Apply' button that reveals the form. Click it
    once if we don't see a form yet. Read-only nudge — no data entered."""
    fields = formreader.read_form(page)
    if fields:
        return fields
    for sel in ("a:has-text('Apply')", "button:has-text('Apply')",
                "a:has-text('Apply for this job')", "#apply_button, .apply-button"):
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=3000)
                page.wait_for_timeout(1500)
                fields = formreader.read_form(page)
                if fields:
                    return fields
        except Exception:
            continue
    return fields


def dry_run(job: dict) -> dict:
    """job needs id, apply_url, title, company_name. Returns a preview dict (see keys below).
    status: ready | needs_input | blocked | error."""
    job_id, url = job["id"], job.get("apply_url")
    if not url:
        return {"job_id": job_id, "status": "error", "reason": "no apply URL for this job"}
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    shot = shot_path(job_id)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 1600},
                                  user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                                              "Chrome/124.0 Safari/537.36"))
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)                 # let ATS JS render the form
            block = _blocker(page)
            fields = _reach_form(page)
            try:                                        # full-page can time out on tall lazy pages -> fall back to viewport
                page.screenshot(path=str(shot), full_page=True, timeout=12000)
            except Exception:
                try:
                    page.screenshot(path=str(shot), full_page=False, timeout=8000)
                except Exception:
                    shot = None
            if block and not fields:
                return {"job_id": job_id, "status": "blocked", "reason": block,
                        "shot": bool(shot), "filled": [], "open": [], "field_count": 0}
            plan = mapping.map_fields(load_kit(), fields)
            status = ("needs_input" if plan["open"] else "ready") if fields else "blocked"
            reason = None if fields else (block or "no form found at apply URL (may need an ATS adapter)")
            return {"job_id": job_id, "status": status, "reason": reason, "shot": bool(shot),
                    "field_count": len(fields), "filled": plan["filled"], "open": plan["open"]}
        except Exception as e:
            return {"job_id": job_id, "status": "error", "reason": f"{type(e).__name__}: {e}",
                    "shot": shot.exists() if shot else False, "filled": [], "open": [], "field_count": 0}
        finally:
            browser.close()

"""Assisted review-and-submit. Opens a VISIBLE browser, fills the form from the kit, then hands it
to the user: they review every field and click Submit themselves. This module never clicks Submit —
it only watches the page and, when it sees the employer's confirmation, reports the application as
submitted so the counter moves on a *real* submit. The human is the one who applies, every time.

Runs the Playwright sync API in a background thread (one session), so the HTTP call that starts it
returns immediately and the browser stays interactive."""

from __future__ import annotations

import threading

import re

from ..apply_kit import load_kit, save_kit
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


# Standard/PII fields already in the kit — never learn these into the answer library.
_STANDARD = re.compile(
    r"\b(first|last|full|legal|preferred)?\s*name\b|email|phone|mobile|resume|\bcv\b|linkedin|github|"
    r"portfolio|website|address|city|state|country|zip|postal|locat|salary|compensation", re.I)


def _fill_all(page, kit, jctx) -> tuple[set, dict]:
    """Fill the form; return (open_labels, filled_snapshot) so we can later learn what the user changed
    or answered themselves."""
    fields = formreader.read_form(page)
    if not fields:
        return set(), {}
    plan = mapping.map_fields(kit, fields)
    plan, still_open = answers.resolve(kit, plan, jctx)
    filler.fill(page, plan)
    open_labels = {(q.get("label") or "").strip().lower() for q in still_open if q.get("label")}
    snap = {(f.get("label") or "").strip().lower(): str(f.get("option") or f.get("value") or "")
            for f in plan["filled"]}
    return open_labels, snap


def _learn(kit, final_answers: list, open_labels: set, snap: dict) -> int:
    """Save what the user did: their answer to a custom question we couldn't fill, or a correction to
    one we filled wrong — into the kit's answer_library so future runs auto-fill it. Skips standard
    PII fields (already in the kit). Returns how many answers were learned."""
    learned = {}
    for a in (final_answers or []):
        label = (a.get("label") or "").strip()
        value = (a.get("value") or "").strip()
        low = label.lower()
        if not label or not value or _STANDARD.search(low):
            continue
        prev = snap.get(low)                          # what we auto-filled (None if we didn't/couldn't)
        if prev is None or prev.strip().lower() != value.lower():
            learned[label] = value                    # custom Q the user answered, a field we missed, or a correction
    if not learned:
        return 0
    lib = dict(kit.answer_library or {})
    lib.update(learned)
    save_kit({"answer_library": lib})
    return len(learned)


def _heal(page, kit, jctx, flagged: list[str]) -> int:
    """Re-fill only the fields the form's validation flagged (targeted, so we never clobber a value
    the user edited on some OTHER field). Returns how many we could fill."""
    fields = formreader.read_form(page)
    if not fields:
        return 0
    plan = mapping.map_fields(kit, fields)
    plan, _ = answers.resolve(kit, plan, jctx)
    fl = [f.lower() for f in flagged]
    targeted = [e for e in plan["filled"]
                if any(x in (e.get("label") or "").lower() or (e.get("label") or "").lower() in x for x in fl)]
    if not targeted:
        return 0
    res = filler.fill(page, {"filled": targeted})
    return len(res.get("entered", []))


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
            kit = load_kit()
            jctx = {"title": job.get("title"), "company": job.get("company_name")}
            open_labels, snap = ((set(), {}) if not formreader.read_form(page)
                                 else _fill_all(page, kit, jctx))
            _set(job_id, "review", "Filled — review/finish every field, then click Submit. Jobber learns "
                                   "what you type or pick and auto-fills it next time.")
            # watch for submission (never submit for them). If validation catches it, self-heal the
            # flagged fields, then wait for the re-submit. ~12 min, or until they close it. Keep a
            # rolling snapshot of the form's answers so we can learn even if they close without a confirm.
            heals, seen, last, tick = 0, set(), [], 0
            for _ in range(360):
                page.wait_for_timeout(2000)
                try:
                    if confirmed(page):
                        _set(job_id, "submitted", "Confirmation detected — marked as applied.")
                        try:
                            on_confirm(job_id)
                        except Exception:
                            pass
                        got = _learn(kit, filler.read_answers(page), open_labels, snap)   # learn from the submitted form
                        if got:
                            _set(job_id, "submitted", f"Applied — learned {got} of your answers for next time.")
                        page.wait_for_timeout(3000)
                        break
                    if heals < 4:                           # validation-error field discovery + self-heal
                        flagged = filler.flagged_fields(page)
                        sig = tuple(sorted(flagged))
                        if flagged and sig not in seen:
                            seen.add(sig)
                            n = _heal(page, kit, jctx, flagged)
                            heals += 1
                            if n:
                                _set(job_id, "review", f"The form flagged {len(flagged)} field(s); "
                                     f"Jobber auto-filled {n} — click Submit again.")
                    tick += 1
                    if tick % 3 == 0:                       # ~every 6s, remember what's on the form
                        snap_now = filler.read_answers(page)
                        if snap_now:
                            last = snap_now
                    _ = page.title()                        # raises if the user closed the window
                except Exception:
                    _learn(kit, last, open_labels, snap)    # learn from the last snapshot before it closed
                    _set(job_id, "closed", "Browser closed. Learned your answers where possible.")
                    break
            else:
                _learn(kit, last, open_labels, snap)
                _set(job_id, "closed", "Timed out waiting for submission.")
            try:
                browser.close()
            except Exception:
                pass
    except Exception as e:
        _set(job_id, "error", f"{type(e).__name__}: {str(e)[:160]}")

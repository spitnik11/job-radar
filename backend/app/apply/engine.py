"""Apply engine. Two entry points:
  dry_run(job)     — read + map + screenshot, no interaction (Phase A preview).
  prepare(job)     — actually fill the live form, read back every required field's state, classify
                     every blocker that would stop a submission, screenshot, and report whether the
                     form is submission-ready. It stops at the armed Submit button — it never clicks
                     it. Firing the real application is a human action (review the screenshot, then
                     submit), by design: an application is irreversible and lands under the user's name.
Playwright sync API — call from a threadpool (a plain `def` FastAPI route), not the event loop."""

from __future__ import annotations

from ..apply_kit import load_kit
from ..config import DATA_DIR
from . import answers, filler, formreader, mapping

SHOTS_DIR = DATA_DIR / "apply_shots"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def shot_path(job_id: str):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_id)
    return SHOTS_DIR / f"{safe}.png"


# ---- blocker detection -------------------------------------------------------------------------

# A *visible, sized* captcha challenge blocks submission. The invisible reCAPTCHA v3 badge
# (.grecaptcha-badge, ~256x60) and off-screen v2-invisible widgets do NOT — they let you submit —
# so presence alone must never be treated as a blocker (it was falsely blocking every GH/Lever form).
_CHALLENGE_JS = r"""
() => {
  const big = el => { const r = el.getBoundingClientRect();
    return getComputedStyle(el).visibility !== 'hidden' && r.width >= 200 && r.height >= 150; };
  for (const f of document.querySelectorAll('iframe')) {
    const s = (f.src||'').toLowerCase(), t = (f.title||'').toLowerCase();
    if ((s.includes('recaptcha') || s.includes('hcaptcha') || s.includes('turnstile') || t.includes('captcha')) && big(f))
      return true;                                  // an actual challenge dialog is showing
  }
  return [...document.querySelectorAll('.h-captcha, .cf-turnstile')].some(big);
}
"""


def _captcha_or_login(page) -> str | None:
    url = (page.url or "").lower()
    if any(w in url for w in ("login", "signin", "sign-in", "/auth")):
        return "login required"
    try:
        if page.evaluate(_CHALLENGE_JS):
            return "CAPTCHA / bot-check challenge visible"
        body = (page.inner_text("body")[:5000] or "").lower()
    except Exception:
        return None
    if any(h in body for h in ("verify you are human", "i'm not a robot", "please complete the captcha")):
        return "CAPTCHA / bot-check challenge visible"
    if any(h in body for h in ("sign in to apply", "log in to apply", "create an account to apply")):
        return "login / account required"
    return None


# Finds the most likely submit control and whether it's usable, flags a multi-step form (a
# Next/Continue with no Submit), and collects any visible validation errors.
_SUBMIT_JS = r"""
() => {
  const txt = el => (el.innerText || el.value || '').trim().toLowerCase();
  const all = [...document.querySelectorAll('button, input[type=submit], [role=button]')];
  const isSub = t => /(submit|send).*(application)?|apply\s*(now)?$|^apply$|^submit$/.test(t);
  const isNext = t => /^(next|continue)\b/.test(t);
  let submit = all.find(el => isSub(txt(el)));
  const next = all.find(el => isNext(txt(el)));
  const errs = [...document.querySelectorAll('[aria-invalid=true], .error:not(:empty), '
      + '[class*="error"]:not(:empty), [class*="invalid"]:not(:empty)')]
      .map(e => (e.innerText||'').trim()).filter(t => t && t.length < 160).slice(0, 8);
  return {
    hasSubmit: !!submit,
    submitDisabled: submit ? (submit.disabled || submit.getAttribute('aria-disabled')==='true') : false,
    submitText: submit ? (submit.innerText||submit.value||'').trim().slice(0,40) : '',
    multiStep: !submit && !!next,
    errors: [...new Set(errs)],
  };
}
"""


def _reach_form(page):
    fields = formreader.read_form(page)
    if fields:
        return fields
    for sel in ("text=Apply for this job", "text=Apply now", "button:has-text('Apply')",
                "a:has-text('Apply')", "#apply_button", ".apply-button"):
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


def _screenshot(page, shot):
    try:
        page.screenshot(path=str(shot), full_page=True, timeout=12000); return True
    except Exception:
        try:
            page.screenshot(path=str(shot), full_page=False, timeout=8000); return True
        except Exception:
            return False


# ---- entry points ------------------------------------------------------------------------------

def dry_run(job: dict, kit=None) -> dict:
    return _run(job, fill=False, kit=kit)


def prepare(job: dict, kit=None) -> dict:
    return _run(job, fill=True, kit=kit)


def _run(job: dict, *, fill: bool, kit=None) -> dict:
    job_id, url = job["id"], job.get("apply_url")
    base = {"job_id": job_id, "filled": [], "open": [], "blockers": [], "field_count": 0}
    if not url:
        return {**base, "status": "error", "reason": "no apply URL for this job"}
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    shot = shot_path(job_id)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 1600}, user_agent=_UA)
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            block = _captcha_or_login(page)
            fields = _reach_form(page)
            if kit is None:
                kit = load_kit()

            if not fields:
                _screenshot(page, shot)
                return {**base, "status": "blocked", "shot": True,
                        "reason": block or "no form found at apply URL (needs an ATS adapter or is login-walled)",
                        "blockers": [block or "no reachable form"]}

            plan = mapping.map_fields(kit, fields)
            jctx = {"title": job.get("title"), "company": job.get("company_name"),
                    "description": job.get("description", "")}
            plan, still_open = answers.resolve(kit, plan, jctx)

            if not fill:                                 # Phase A preview — no interaction
                _screenshot(page, shot)
                status = "needs_input" if still_open else "ready"
                return {**base, "status": status, "shot": True, "field_count": len(fields),
                        "filled": plan["filled"], "open": still_open, "reason": block}

            # Phase B: fill the real form, then read back the truth about what's still missing
            fillres = filler.fill(page, plan)
            page.wait_for_timeout(600)
            missing = filler.missing_required(page, fields)
            if missing:
                # a re-render (Ashby-style) can wipe fields we already filled. Re-read fresh, re-map,
                # and re-fill only the still-missing ones (no LLM re-run), then re-check once.
                missing = _reconcile(page, kit, missing)
            sub = page.evaluate(_SUBMIT_JS)
            _screenshot(page, shot)

            blockers = _classify(block, fillres, missing, sub, still_open)
            status = "blocked" if blockers else "ready_to_submit"
            reason = (blockers[0] if blockers
                      else "all required fields satisfied; submit button armed — review the screenshot, then submit")
            return {**base, "status": status, "shot": True, "field_count": len(fields),
                    "filled": plan["filled"], "open": still_open, "blockers": blockers,
                    "reason": reason, "submit_text": sub.get("submitText", ""),
                    "entered": len(fillres["entered"])}
        except Exception as e:
            ok = _screenshot(page, shot)
            return {**base, "status": "error", "shot": ok,
                    "reason": f"{type(e).__name__}: {str(e)[:180]}", "blockers": ["engine error"]}
        finally:
            browser.close()


def _reconcile(page, kit, missing: list[str]) -> list[str]:
    """Re-fill required fields a re-render wiped after the first pass, then re-check. One pass only:
    re-read the current form, re-map the kit onto it, and enter only the fields whose label is still
    in `missing` (deterministic values only — never re-invokes the LLM answer-tier)."""
    fresh = formreader.read_form(page)
    if not fresh:
        return missing
    plan2 = mapping.map_fields(kit, fresh)
    miss_lc = [m.lower() for m in missing]
    refill = [f for f in plan2["filled"]
              if any(m in (f.get("label") or "").lower() or (f.get("label") or "").lower() in m
                     for m in miss_lc)]
    if not refill:
        return missing
    filler.fill(page, {"filled": refill})
    page.wait_for_timeout(500)
    return filler.missing_required(page, fresh)


def _classify(block, fillres, missing, sub, still_open) -> list[str]:
    """Every condition that would stop this application from submitting cleanly."""
    b = []
    if block:
        b.append(block)
    for f in fillres["failed"]:
        b.append(f"couldn't fill: {f['label']} ({f['reason']})")
    if missing:
        b.append("required field(s) still empty: " + ", ".join(missing[:6]) + ("…" if len(missing) > 6 else ""))
    req_open = [q for q in still_open if q.get("required")]
    if req_open:
        b.append(f"{len(req_open)} required question(s) need an answer: "
                 + "; ".join((q.get("label") or "")[:40] for q in req_open[:4]))
    if sub.get("multiStep"):
        b.append("multi-step form (a Next/Continue step before Submit) — not yet handled")
    if not sub.get("hasSubmit"):
        b.append("no submit button found on the form")
    elif sub.get("submitDisabled"):
        b.append("submit button is disabled")
    if sub.get("errors"):
        b.append("form shows validation error(s): " + " | ".join(sub["errors"][:3]))
    return b

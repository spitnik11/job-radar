"""Email-based application tracker. Polls a mailbox over long intervals (IMAP), matches each
message to a job in the Applied pipeline using MULTIPLE signals (company, title, sender, body —
never sender alone), and classifies Offer/Rejected from multi-signal keyword+context.

Gated on IMAP creds in backend/data/secrets.local.yaml (inert without, like USAJOBS). No new deps —
Python's imaplib + email. The classify/match functions are pure and unit-tested without a mailbox."""

from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Optional

from .config import DATA_DIR
from .repository import SQLiteJobRepository

# in-progress statuses we try to resolve from email
IN_PROGRESS = ["APPLIED", "PHONE_SCREEN", "INTERVIEW", "FINAL_INTERVIEW"]

# weighted phrases — classification needs a COMBINED score, not a single keyword (spec)
OFFER_SIGNALS = [
    ("pleased to offer", 3), ("offer of employment", 3), ("extend an offer", 3),
    ("excited to offer", 3), ("offer letter", 3), ("formal offer", 3),
    ("welcome to the team", 2), ("job offer", 2), ("your offer", 2),
    ("congratulations", 1), ("compensation package", 1), ("start date", 1),
]
REJECT_SIGNALS = [
    ("regret to inform", 3), ("not moving forward", 3), ("will not be moving forward", 3),
    ("not be proceeding", 3), ("pursue other candidates", 3), ("other candidates", 2),
    ("no longer under consideration", 3), ("decided not to proceed", 3),
    ("position has been filled", 2), ("not selected", 2), ("not to move forward", 3),
    ("unfortunately", 1), ("wish you the best", 1), ("future opportunities", 1),
]


def classify(subject: str, body: str) -> tuple[Optional[str], int]:
    """(status, confidence). Requires a combined score >= 2 so a lone keyword can't decide."""
    text = f"{subject}\n{body}".lower()
    off = sum(w for kw, w in OFFER_SIGNALS if kw in text)
    rej = sum(w for kw, w in REJECT_SIGNALS if kw in text)
    if off >= 2 and off > rej:
        return "OFFER", off
    if rej >= 2 and rej > off:
        return "REJECTED", rej
    return None, 0


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def match_score(sender: str, subject: str, body: str, job) -> int:
    """Signal-based match — company, domain, title tokens, sender. Never sender alone."""
    text = f"{subject}\n{body}".lower()
    frm = (sender or "").lower()
    score = 0
    comp = (job.company_name or "").lower().strip()
    if comp and (comp in text or (len(comp) > 3 and _norm(comp) in _norm(frm))):
        score += 3
    if job.company_domain and job.company_domain.lower() in frm:
        score += 3
    title_tokens = [t for t in re.findall(r"[a-z]+", (job.title or "").lower()) if len(t) > 3]
    hits = sum(1 for t in set(title_tokens) if t in text)
    score += 2 if hits >= 2 else hits
    return score


def match_email(sender: str, subject: str, body: str, jobs: list) -> Optional[object]:
    best, best_score = None, 0
    for j in jobs:
        s = match_score(sender, subject, body, j)
        if s > best_score:
            best, best_score = j, s
    return best if best_score >= 3 else None      # need >=1 strong or multiple weak signals


# ---------------- IMAP polling (gated on creds) ----------------

def creds() -> Optional[dict]:
    import yaml
    f = DATA_DIR / "secrets.local.yaml"
    if not f.exists():
        return None
    e = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("email") or {}
    if e.get("host") and e.get("user") and e.get("password"):
        return {"host": e["host"], "user": e["user"], "password": e["password"],
                "folder": e.get("folder", "INBOX"), "since_days": int(e.get("since_days", 30))}
    return None


def _decode(v) -> str:
    if not v:
        return ""
    parts = decode_header(v)
    out = []
    for text, enc in parts:
        out.append(text.decode(enc or "utf-8", "ignore") if isinstance(text, bytes) else text)
    return "".join(out)


def _body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                except (AttributeError, UnicodeDecodeError):
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
    except (AttributeError, UnicodeDecodeError):
        return ""


def check() -> dict:
    """Poll the mailbox once: match recent emails to in-progress applications, classify, update."""
    c = creds()
    if not c:
        return {"enabled": False, "checked": 0, "matched": 0, "updated": 0}
    repo = SQLiteJobRepository()
    jobs = repo.list_jobs(status_in=IN_PROGRESS, limit=999)
    if not jobs:
        return {"enabled": True, "checked": 0, "matched": 0, "updated": 0}

    checked = matched = updated = 0
    try:
        M = imaplib.IMAP4_SSL(c["host"])
        M.login(c["user"], c["password"])
        M.select(c["folder"])
        since = (datetime.now(timezone.utc) - timedelta(days=c["since_days"])).strftime("%d-%b-%Y")
        _, data = M.search(None, f'(SINCE {since})')
        for num in data[0].split():
            _, raw = M.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            checked += 1
            sender = _decode(msg.get("From"))
            subject = _decode(msg.get("Subject"))
            body = _body_text(msg)
            job = match_email(sender, subject, body, jobs)
            if not job:
                continue
            matched += 1
            status, conf = classify(subject, body)
            if status and job.status != status:
                repo.set_status(job.id, status)
                repo.add_note(job.id, f"Auto: email '{subject[:80]}' → {status} (confidence {conf})")
                job.status = status                    # so we don't re-match the same job this run
                updated += 1
        M.logout()
    except Exception as exc:  # noqa: BLE001 — never let a mail hiccup crash the app
        return {"enabled": True, "error": str(exc), "checked": checked,
                "matched": matched, "updated": updated}
    return {"enabled": True, "checked": checked, "matched": matched, "updated": updated}

"""Hard-scam guard (spec section 24). Phase-0 stub: a keyword quarantine only.

# ponytail: every Phase-0 source is a direct-employer ATS (trust=100 by construction), so
# there is almost nothing to catch here yet. The full trust/scam subsystem (soft signals,
# source verification, risk scoring) earns its place when the first UNTRUSTED source
# (JobSpy / arbitrary-site JSON-LD) lands. Keep this stub cheap until then.
"""

from __future__ import annotations

from typing import Optional

HARD_SCAM_PHRASES = (
    "payment to apply", "pay to apply", "training fee", "registration fee",
    "gift card", "gift cards", "crypto payment", "pay in crypto",
    "cash a check", "deposit a check", "wire transfer to", "western union",
    "whatsapp only", "telegram only", "text me on whatsapp", "contact me on telegram",
    "bank account information", "provide your ssn", "social security number to start",
)


def is_hard_scam(text: str) -> tuple[bool, Optional[str]]:
    low = text.lower()
    for phrase in HARD_SCAM_PHRASES:
        if phrase in low:
            return True, f"scam signal: '{phrase}'"
    return False, None

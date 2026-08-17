"""Seniority + experience parsing (spec section 6). The required-vs-preferred distinction is
the whole point: '5 years required' penalizes hard, '3-5 years preferred / or equivalent' does not."""

from __future__ import annotations

import re
from typing import Optional

# ranges first ("3-5 years"), then singletons ("5+ years")
_YEARS_RANGE = re.compile(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)")
_YEARS_ONE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yoe)")

_REQUIRED_WORDS = ("required", "must have", "must possess", "minimum", "at least", "requires")
_PREFERRED_WORDS = ("preferred", "nice to have", "a plus", "ideally", "bonus", "or equivalent",
                    "desired", "would be great")

_HIDE_TITLES = ("staff", "principal", "director", "vice president", "vp ", " vp",
                "head of", "manager", "mgr")
_SENIOR_TITLES = ("senior", "sr.", "sr ", " sr", "lead ")
_JUNIOR_TITLES = ("junior", "jr.", "jr ", "associate", "entry level", "entry-level", "intern")


def parse_experience(text: str) -> tuple[Optional[int], Optional[int], bool]:
    """Return (min_years, max_years, required). required=False means only 'preferred' seen."""
    low = text.lower()
    hits: list[tuple[int, int, bool]] = []  # (low, high, required)

    def _required_near(pos: int) -> bool:
        window = low[max(0, pos - 60): pos + 60]
        if any(w in window for w in _PREFERRED_WORDS):
            return False
        if any(w in window for w in _REQUIRED_WORDS):
            return True
        return True  # a bare "5 years experience" reads as a requirement

    for m in _YEARS_RANGE.finditer(low):
        lo, hi = int(m.group(1)), int(m.group(2))
        hits.append((lo, hi, _required_near(m.start())))
    # singletons not already covered by a range match
    for m in _YEARS_ONE.finditer(low):
        # skip if this number is the tail of a range we already caught
        if _YEARS_RANGE.search(low[max(0, m.start() - 8): m.end()]):
            continue
        n = int(m.group(1))
        hits.append((n, n, _required_near(m.start())))

    if not hits:
        return None, None, False

    required_hits = [h for h in hits if h[2]]
    chosen = required_hits or hits
    lo = min(h[0] for h in chosen)
    hi = max(h[1] for h in chosen)
    return lo, hi, bool(required_hits)


def classify_seniority(title: str) -> str:
    t = f" {title.lower()} "
    if "intern" in t:
        return "intern"
    if "principal" in t:
        return "principal"
    if "staff" in t:
        return "staff"
    if "director" in t or "vice president" in t or " vp " in t or "head of" in t:
        return "director"
    if "manager" in t or " mgr " in t:
        return "manager"
    if any(w in t for w in _SENIOR_TITLES):
        return "senior"
    if any(w in t for w in _JUNIOR_TITLES):
        return "junior"
    return "mid"


def is_suppressed(seniority: str, required_years_max: Optional[int], required: bool
                  ) -> tuple[bool, Optional[str]]:
    """Hard hide rules (spec section 6). Senior title / 4-5 yrs are penalties, not hides."""
    if seniority in ("staff", "principal", "director", "manager"):
        return True, f"{seniority} role"
    if required and required_years_max is not None and required_years_max >= 6:
        return True, f"{required_years_max}+ years required"
    return False, None

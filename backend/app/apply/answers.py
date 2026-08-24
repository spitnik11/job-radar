"""Answer custom application questions. Tiered by design (kit answer-library → local LLM → escalate),
but only the deterministic library tier is wired now: it never invents an answer, so an unanswered
*required* question stays an honest blocker for review rather than being filled with a guess. The
LLM tiers (Grok default, Claude escalation) slot in at the marked seam without touching callers."""

from __future__ import annotations

from difflib import SequenceMatcher

from ..apply_kit import ApplicationKit

_TEXT = {"text", "textarea", "email", "tel", "url", "number", "search"}


def _from_library(kit: ApplicationKit, question: str) -> str | None:
    """Best matching entry in the user's answer_library (pattern substring or fuzzy >= .6)."""
    lib = kit.answer_library or {}
    if not lib or not question:
        return None
    q = question.lower()
    for pat, ans in lib.items():
        if pat.lower() in q or q in pat.lower():
            return ans
    pat, score = max(((p, SequenceMatcher(None, q, p.lower()).ratio()) for p in lib),
                     key=lambda t: t[1], default=(None, 0))
    return lib[pat] if pat and score >= 0.6 else None


def answer(kit: ApplicationKit, question: str) -> str | None:
    ans = _from_library(kit, question)
    if ans is not None:
        return ans
    # --- LLM tier seam: local Ollama field-map -> Grok custom-Q -> Claude escalate goes here. ---
    return None


def resolve(kit: ApplicationKit, plan: dict) -> tuple[dict, list[dict]]:
    """Fill answerable free-text open questions from the library; return (plan, still_open).
    Non-text questions (dropdowns/checkbox we couldn't match) and unanswered ones stay open."""
    still_open = []
    for q in plan.get("open", []):
        if q.get("type") in _TEXT and not q.get("options"):
            a = answer(kit, q.get("label") or "")
            if a is not None:
                plan["filled"].append({"label": q.get("label"), "value": a, "option": None,
                                       "type": q.get("type"), "jr": q.get("jr"),
                                       "required": q.get("required", False)})
                continue
        still_open.append(q)
    return plan, still_open

"""Answer custom application questions, tiered by trust:
  1. the user's answer_library         — authoritative, exact/fuzzy match, always wins.
  2. sensitive-question guard          — legal/eligibility/background questions are NEVER machine-guessed;
                                         they fall through to the library or stay a review blocker.
  3. local LLM (Ollama), grounded      — only for open-ended, non-sensitive prose (essays, "why us").
                                         Grounded in the résumé; must answer UNKNOWN rather than invent.
An unanswered *required* question stays an honest blocker — we never fabricate to get past a form."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from ..apply_kit import ApplicationKit

_TEXT = {"text", "textarea", "email", "tel", "url", "number", "search", ""}
_OLLAMA = "http://localhost:11434"

# Questions whose wrong answer has legal/eligibility consequences — never let an LLM guess these.
_SENSITIVE = re.compile(
    r"sponsor|visa|authoriz|eligible to work|right to work|legally|citizen|felony|convict|"
    r"criminal|background check|drug (test|screen)|non-?compete|employment agreement|"
    r"restrict|clearance|export control|itar|18 years|over 18|veteran|disab|gender|race|ethnic",
    re.I)

_resume_cache: dict[str, str] = {}


def _resume_text(kit: ApplicationKit) -> str:
    p = (kit.resume_path or "").strip()
    if not p or not Path(p).is_file():
        return ""
    key = f"{p}:{Path(p).stat().st_mtime_ns}"
    if key not in _resume_cache:
        try:
            from ..resume_parser import extract_text
            _resume_cache.clear()
            _resume_cache[key] = extract_text(Path(p).read_bytes(), Path(p).name)[:4000]
        except Exception:
            _resume_cache[key] = ""
    return _resume_cache[key]


def _from_library(kit: ApplicationKit, question: str) -> str | None:
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


def _chat_model() -> str | None:
    try:
        tags = httpx.get(f"{_OLLAMA}/api/tags", timeout=3).json().get("models", [])
    except Exception:
        return None
    names = [m["name"] for m in tags if "embed" not in m["name"].lower()]
    for pref in ("llama3.2", "qwen2.5", "qwen3", "llama3", "mistral", "phi"):
        m = next((n for n in names if n.startswith(pref)), None)
        if m:
            return m
    return names[0] if names else None


def _llm_answer(kit: ApplicationKit, question: str, job: dict | None) -> str | None:
    model = _chat_model()
    resume = _resume_text(kit)
    if not model or not resume:
        return None
    j = job or {}
    prompt = (
        f"You are filling a job application for {kit.full_name}. "
        f"Role: {j.get('title','')} at {j.get('company','')}.\n"
        f"Answer this application question in the first person, concise (2-4 sentences), "
        f"honest, and grounded ONLY in the résumé below. Do not invent facts. "
        f"If the résumé does not support an answer, reply with exactly: UNKNOWN\n\n"
        f"Question: {question}\n\nRésumé:\n{resume}\n\nAnswer:")
    try:
        r = httpx.post(f"{_OLLAMA}/api/generate",
                       json={"model": model, "prompt": prompt, "stream": False,
                             "options": {"temperature": 0.4, "num_predict": 220}},
                       timeout=90)                   # first call cold-loads the model into VRAM (~30-60s)
        out = (r.json().get("response") or "").strip()
    except Exception:
        return None
    if not out or "UNKNOWN" in out or len(out) < 8:
        return None
    return out


def answer(kit: ApplicationKit, question: str, job: dict | None = None) -> str | None:
    lib = _from_library(kit, question)
    if lib is not None:
        return lib
    if _SENSITIVE.search(question or ""):
        return None                                 # never machine-guess a legal/eligibility question
    return _llm_answer(kit, question, job)


def resolve(kit: ApplicationKit, plan: dict, job: dict | None = None) -> tuple[dict, list[dict]]:
    """Fill answerable free-text open questions; return (plan, still_open). Dropdowns/checkboxes we
    couldn't match and anything unanswered stay open (a required one remains a real blocker)."""
    still_open = []
    for q in plan.get("open", []):
        if q.get("type") in _TEXT and not q.get("options"):
            a = answer(kit, q.get("label") or "", job)
            if a is not None:
                plan["filled"].append({"label": q.get("label"), "value": a, "option": None,
                                       "type": q.get("type") or "textarea", "jr": q.get("jr"),
                                       "required": q.get("required", False), "answered_by": "ai"})
                continue
        still_open.append(q)
    return plan, still_open

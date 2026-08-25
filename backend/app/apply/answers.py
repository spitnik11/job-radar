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


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().rstrip("*").strip().lower()


def _from_library(kit: ApplicationKit, question: str) -> str | None:
    lib = kit.answer_library or {}
    if not lib or not question:
        return None
    q = _norm(question)                              # normalize whitespace/asterisk on both sides
    for pat, ans in lib.items():
        pn = _norm(pat)
        if pn and (pn in q or q in pn):
            return ans
    pat, score = max(((p, SequenceMatcher(None, q, _norm(p)).ratio()) for p in lib),
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


def _generate(prompt: str, num_predict: int = 220) -> str | None:
    model = _chat_model()
    if not model:
        return None
    try:
        r = httpx.post(f"{_OLLAMA}/api/generate",
                       json={"model": model, "prompt": prompt, "stream": False,
                             "options": {"temperature": 0.3, "num_predict": num_predict}},
                       timeout=90)                   # first call cold-loads the model into VRAM (~30-60s)
        return (r.json().get("response") or "").strip()
    except Exception:
        return None


def _llm_answer(kit: ApplicationKit, question: str, job: dict | None) -> str | None:
    resume = _resume_text(kit)
    if not resume:
        return None
    j = job or {}
    out = _generate(
        f"You are filling a job application for {kit.full_name}. "
        f"Role: {j.get('title','')} at {j.get('company','')}.\n"
        f"Answer this application question in the first person, concise (2-4 sentences), "
        f"honest, and grounded ONLY in the résumé below. Do not invent facts. "
        f"If the résumé does not support an answer, reply with exactly: UNKNOWN\n\n"
        f"Question: {question}\n\nRésumé:\n{resume}\n\nAnswer:")
    if not out or "UNKNOWN" in out or len(out) < 8:
        return None
    return out


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 3}


def _best_option(text: str, options: list[str]) -> str | None:
    """Map free text to the closest option: exact → substring → word-overlap → fuzzy. None if nothing
    is a reasonable fit (better to leave a choice open than mis-select)."""
    t = (text or "").strip().lower()
    if not t or not options:
        return None
    for o in options:
        if t == o.lower():
            return o
    for o in options:
        ol = o.lower()
        if ol in t or (len(ol) > 8 and t in ol):
            return o
    tw = _words(t)
    best, score = None, 0.0
    for o in options:                                # fraction of the option's key words present in the text
        ow = _words(o)
        ov = len(tw & ow) / len(ow) if ow else 0
        if ov > score:
            best, score = o, ov
    if score >= 0.6:
        return best
    best, score = None, 0.0
    for o in options:
        rr = SequenceMatcher(None, t, o.lower()).ratio()
        if rr > score:
            best, score = o, rr
    return best if score >= 0.6 else None


def answer_choice(kit: ApplicationKit, question: str, options: list[str], job: dict | None = None) -> str | None:
    """Pick an option for a custom radio/select question — from the user's answer_library ONLY.
    A discrete choice on a real application is consequential (a wrong timezone/eligibility pick can
    auto-reject you), and a small local model isn't reliable enough to make it, so we do NOT let the
    LLM choose here: an unmatched choice stays open for the user's quick review. They can add a rule
    to the library once and it applies automatically after that."""
    lib = _from_library(kit, question)
    if lib is not None:
        return _best_option(lib, options)
    return None


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
        opts = q.get("options") or []
        label = q.get("label") or ""
        if not opts and q.get("type") in _TEXT:              # free-text question
            a = answer(kit, label, job)
            if a is not None:
                plan["filled"].append({"label": q.get("label"), "value": a, "option": None,
                                       "type": q.get("type") or "textarea", "jr": q.get("jr"),
                                       "required": q.get("required", False), "answered_by": "ai"})
                continue
        elif opts and q.get("type") in ("radio", "select-one", "select"):   # custom choice question
            chosen = answer_choice(kit, label, opts, job)
            if chosen is not None:
                jr = q.get("jr")
                if q.get("type") == "radio":
                    jr = (q.get("opt_jrs") or {}).get(chosen)   # the specific option's handle
                if jr is not None:
                    plan["filled"].append({"label": q.get("label"), "value": chosen, "option": chosen,
                                           "type": q.get("type"), "jr": jr,
                                           "required": q.get("required", False), "answered_by": "ai"})
                    continue
        still_open.append(q)
    return plan, still_open

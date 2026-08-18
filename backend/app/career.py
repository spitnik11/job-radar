"""Career feedback from application OUTCOMES (spec). Analyzes only OFFER and REJECTED jobs —
never merely viewed/saved/applied. Aggregates over ALL recorded outcomes each time, so the report
grows sharper and keeps context as more offers/declines accumulate (incremental, not from-scratch)."""

from __future__ import annotations

from collections import Counter

from .config import load_profile
from .repository import SQLiteJobRepository


def _skill_counter(jobs) -> Counter:
    c: Counter = Counter()
    for j in jobs:
        for s in set(j.detected_skills or []):
            c[s] += 1
    return c


def _fmt(skills) -> list[str]:
    return [s.replace("_", " ") for s in skills]


def report() -> dict:
    repo = SQLiteJobRepository()
    offers = repo.list_jobs(status="OFFER", limit=999)
    declines = repo.list_jobs(status="REJECTED", limit=999)
    n_off, n_rej = len(offers), len(declines)
    if n_off + n_rej == 0:
        return {"outcomes": 0, "offers": 0, "declines": 0,
                "message": "Mark a job Offer or Rejected (or connect email) to start the report. "
                           "It sharpens as more outcomes accumulate."}

    have = set(load_profile().skills.keys())
    off_c, rej_c = _skill_counter(offers), _skill_counter(declines)
    all_c = off_c + rej_c

    frequent = [s for s, _ in all_c.most_common(15)]
    linked_offers = [s for s, _ in off_c.most_common(12)]
    linked_declines = [s for s, _ in rej_c.most_common(12)]
    # gaps: skills that show up (esp. in declines) but aren't in the candidate's profile
    gaps = [s for s, _ in (rej_c + all_c).most_common(40) if s not in have][:12]
    # skills that appear in offers but rarely in declines -> correlated with better outcomes
    edge = [s for s in linked_offers if off_c[s] > rej_c.get(s, 0)][:8]

    portfolio = [f"Add a portfolio piece demonstrating {s.replace('_', ' ')}" for s in gaps[:5]]
    projects = [f"Build a project using {s.replace('_', ' ')} "
                f"(requested in {rej_c.get(s, all_c[s])} relevant application(s))" for s in gaps[:5]]

    career = []
    career.append(f"{n_off} offer(s) and {n_rej} decline(s) analyzed.")
    if edge:
        career.append("Skills correlated with your offers: " + ", ".join(_fmt(edge)) + ".")
    if gaps:
        career.append("Recurring skills you're missing (show up in declines): " + ", ".join(_fmt(gaps[:6])) + ".")
    strong = list({j.title for j in offers})[:6]
    if strong:
        career.append("Roles where you're strongest (received offers): " + "; ".join(strong) + ".")
    if n_off + n_rej < 5:
        career.append("Early signal — this becomes more reliable as more outcomes are recorded.")

    return {
        "outcomes": n_off + n_rej, "offers": n_off, "declines": n_rej,
        "key_skills": {
            "frequently_requested": _fmt(frequent),
            "linked_to_offers": _fmt(linked_offers),
            "linked_to_declines": _fmt(linked_declines),
            "gaps": _fmt(gaps),
        },
        "portfolio_suggestions": portfolio,
        "project_suggestions": projects,
        "career_report": career,
    }

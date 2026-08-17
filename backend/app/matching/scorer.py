"""RuleBasedMatchEngine — deterministic, explainable scoring (spec sections 20-21).
Every point is attributable, which is the whole reason this exists instead of an opaque AI %.
Implements interfaces.MatchEngine so a Hybrid/LLM engine can replace it later."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..schemas import CandidateProfile, CanonicalJob, ScoreFactor, ScoreResult
from . import location as loc

WEIGHTS = {
    "role": 25, "skills": 25, "experience": 15, "portfolio": 10,
    "location": 10, "education": 5, "freshness": 5, "source": 5,
}

_TITLE_STOP = {"the", "of", "and", "a", "for", "to", "in", "with"}
_TITLE_NOISE = {"senior", "sr", "junior", "jr", "staff", "principal", "lead", "i", "ii",
                "iii", "iv", "1", "2", "3", "level", "associate"}


def _title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in _TITLE_STOP and w not in _TITLE_NOISE}


def _role_match(title: str, profile: CandidateProfile):
    jt = _title_tokens(title)
    best_sim, best_tier, best_name = 0.0, None, None
    for role in profile.target_roles:
        rt = _title_tokens(role.title)
        if not rt:
            continue
        sim = len(jt & rt) / len(rt)
        if sim > best_sim:
            best_sim, best_tier, best_name = sim, role.tier, role.title
    return best_sim, best_tier, best_name


def _days_old(dt) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def _freshness(days) -> float:
    if days is None:
        return 0.5
    for limit, score in ((1, 1.0), (3, 0.9), (7, 0.8), (14, 0.6), (21, 0.4)):
        if days <= limit:
            return score
    return 0.2


class RuleBasedMatchEngine:
    def score(self, profile: CandidateProfile, job: CanonicalJob) -> ScoreResult:
        text = f"{job.title}\n{job.description_text}".lower()
        detected = set(job.detected_skills)
        owned = {s for s in detected if s in profile.skills}
        missing = detected - owned
        flags: list[str] = []

        # --- role ---
        role_sim, role_tier, role_name = _role_match(job.title, profile)
        role_detail = f"~{role_name} ({role_tier})" if role_name and role_sim >= 0.5 \
            else "no strong target-role match"

        # --- skills ---
        if detected:
            numer = sum(profile.skills[s] for s in owned)
            skills_sim = numer / (numer + 0.7 * len(missing)) if (owned or missing) else 0.0
        else:
            # broad vocab -> no tech skill found reads as a weak (non-technical) match, not neutral
            skills_sim = 0.35
        skills_detail = (
            "have: " + ", ".join(sorted(owned)[:6]) +
            ("; missing: " + ", ".join(sorted(missing)[:4]) if missing else "")
        ) if detected else "no known skills detected"

        # --- experience ---
        exp_sim = 0.9
        if job.years_required and job.required_years_max is not None:
            gap = job.required_years_max - profile.years_experience
            exp_sim = 1.0 if gap <= 0 else 0.8 if gap == 1 else 0.6 if gap == 2 else 0.3
            if job.required_years_max >= 5:
                flags.append(f"{job.required_years_max}+ yrs")
        if job.seniority in ("senior",):
            exp_sim *= 0.6
            flags.append("senior")
        exp_detail = (
            f"{job.required_years_max}+ yrs required vs {profile.years_experience}"
            if job.years_required and job.required_years_max else "no hard experience bar"
        )

        # --- portfolio ---
        port = detected & profile.portfolio_skills
        port_sim = (len(port) / len(detected)) if detected else 0.5
        port_detail = ("project-proven: " + ", ".join(sorted(port)[:5])) if port \
            else "no portfolio-backed skills"

        # --- location ---
        loc_sim, _hard_fail, loc_detail = loc.evaluate(job, profile)
        if job.remote:
            flags.append("remote")

        # --- education ---
        requires_degree = bool(re.search(r"\b(bachelor|degree|b\.?s\.?|b\.?a\.?)\b", text))
        advanced = bool(re.search(r"\b(master|phd|ph\.d)\b", text))
        has_degree = profile.education_level in ("bachelor", "master", "phd")
        edu_sim = 0.6 if (advanced and profile.education_level == "bachelor") \
            else 1.0 if (has_degree or not requires_degree) else 0.5
        edu_detail = "advanced degree wanted" if advanced else \
            ("degree required — have B.A.S." if requires_degree else "no degree requirement")

        # --- freshness / source ---
        days = _days_old(job.date_posted)
        fresh_sim = _freshness(days)
        source_sim = 1.0  # Phase 0: all direct-employer ATS
        if job.salary_min:
            flags.append("salary")

        sims = {
            "role": role_sim, "skills": skills_sim, "experience": exp_sim,
            "portfolio": port_sim, "location": loc_sim, "education": edu_sim,
            "freshness": fresh_sim, "source": source_sim,
        }
        details = {
            "role": role_detail, "skills": skills_detail, "experience": exp_detail,
            "portfolio": port_detail, "location": loc_detail, "education": edu_detail,
            "freshness": f"{days:.0f}d old" if days is not None else "date unknown",
            "source": "direct employer ATS",
        }
        breakdown = [
            ScoreFactor(factor=k, got=round(min(1.0, sims[k]) * WEIGHTS[k], 1),
                        max=WEIGHTS[k], detail=details[k])
            for k in WEIGHTS
        ]
        relevance = round(sum(f.got for f in breakdown))
        relevance = max(0, min(100, relevance))

        # --- priority (spec section 21): qualification + application value ---
        pr = relevance
        if days is not None:
            if days <= 1:
                pr += 8
            elif days <= 3:
                pr += 5
            elif days > 21:
                pr -= 8
        pr += 5  # direct company source
        if job.remote:
            pr += 2
        if job.salary_min:
            pr += 2
        if role_tier == "A" and role_sim >= 0.5:
            pr += 5
        if job.seniority in ("junior", "intern"):
            pr += 5
        if job.years_required and job.required_years_max and job.required_years_max >= 5:
            pr -= 10
        priority = max(0, min(100, pr))

        return ScoreResult(
            relevance=relevance, priority=priority, breakdown=breakdown, flags=flags,
        )

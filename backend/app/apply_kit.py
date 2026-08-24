"""Application Kit — the structured info every auto-application fills from (spec: gather & organize
all application data). Stored locally in data/apply_kit.local.json (gitignored, treated like a
secret: PII + résumé path). Voluntary EEO fields default to 'Decline to self-identify' and are only
ever what the user explicitly sets — never fabricated."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from .config import DATA_DIR

KIT_FILE = DATA_DIR / "apply_kit.local.json"
DECLINE = "Decline to self-identify"

# Casual self-ID inputs -> the standard option text used on Greenhouse/Lever/Ashby EEO dropdowns,
# so an application answer matches without the agent guessing. Substring, case-insensitive; the
# user's original value is kept verbatim if nothing matches (never fabricate a category).
_EEO_CANON = {
    "gender": {"male": "Male", "man": "Male", "female": "Female", "woman": "Female",
               "non-binary": "Non-binary", "nonbinary": "Non-binary"},
    "race": {"black": "Black or African American", "african": "Black or African American",
             "white": "White", "hispanic": "Hispanic or Latino", "latino": "Hispanic or Latino",
             "latina": "Hispanic or Latino", "asian": "Asian",
             "native american": "American Indian or Alaska Native",
             "american indian": "American Indian or Alaska Native",
             "pacific": "Native Hawaiian or Other Pacific Islander",
             "two or more": "Two or More Races", "mixed": "Two or More Races"},
    "veteran_status": {"not a veteran": "I am not a protected veteran", "not a protected": "I am not a protected veteran",
                       "no": "I am not a protected veteran",
                       "veteran": "I identify as one or more of the classifications of a protected veteran",
                       "yes": "I identify as one or more of the classifications of a protected veteran"},
    "disability_status": {"not disabled": "No, I do not have a disability", "no": "No, I do not have a disability",
                          "none": "No, I do not have a disability",
                          "disabled": "Yes, I have a disability", "yes": "Yes, I have a disability"},
}


def _canon(field: str, value: str) -> str:
    v = (value or "").strip()
    if not v or v == DECLINE:
        return v or DECLINE
    low = v.lower()
    for key, canon in _EEO_CANON[field].items():   # first substring hit wins (specific keys first)
        if key in low:
            return canon
    return v                                        # unknown -> keep the user's own words


def _normalize(kit: "ApplicationKit") -> "ApplicationKit":
    # Windows "Copy as path" wraps the path in quotes -> strip them or the file upload can't find it.
    kit.resume_path = kit.resume_path.strip().strip('"').strip("'").strip()
    for f in _EEO_CANON:
        setattr(kit, f, _canon(f, getattr(kit, f)))
    return kit


class ApplicationKit(BaseModel):
    # identity / contact
    full_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    state: str = ""
    country: str = "United States"
    address: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    # résumé (local file to upload) — kept as a path, never inlined into logs
    resume_path: str = ""
    # work authorization
    authorized_us: Optional[bool] = None
    needs_sponsorship: Optional[bool] = None
    # logistics
    willing_relocate: Optional[bool] = None
    work_pref: str = ""                 # remote | hybrid | onsite | any
    start_date: str = ""                # e.g. "2 weeks"
    desired_salary: str = ""            # or "Negotiable"
    # voluntary EEO self-ID (honest, optional, default decline)
    gender: str = DECLINE
    race: str = DECLINE
    veteran_status: str = DECLINE
    disability_status: str = DECLINE
    # common screeners
    years_experience: Optional[int] = None
    education_level: str = ""
    hear_about_us: str = ""
    references_available: Optional[bool] = None
    # cover letters / long answers
    cover_letter_mode: str = "tailored"     # tailored | template | skip
    cover_letter_template: str = ""
    # learned answers (question-pattern -> preferred answer) + free-form edge cases
    answer_library: dict[str, str] = {}
    notes: str = ""


def load_kit() -> ApplicationKit:
    if KIT_FILE.exists():
        try:
            return ApplicationKit(**json.loads(KIT_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError):
            return ApplicationKit()
    return ApplicationKit()


def save_kit(data: dict) -> ApplicationKit:
    kit = _normalize(ApplicationKit(**{**load_kit().model_dump(), **data}))   # merge onto existing
    KIT_FILE.write_text(json.dumps(kit.model_dump(), indent=2), encoding="utf-8")
    return kit


def missing_fields() -> list[str]:
    """What still needs to be filled before auto-apply can run (the essentials)."""
    k = load_kit()
    need = []
    if not k.full_name: need.append("full name")
    if not k.email: need.append("email")
    if not k.phone: need.append("phone")
    if not (k.city and k.state): need.append("location")
    if not k.resume_path:
        need.append("résumé file")
    elif not Path(k.resume_path).is_file():
        need.append("résumé file (path not found on disk)")
    if k.authorized_us is None: need.append("work authorization")
    return need


def is_ready() -> bool:
    return not missing_fields()

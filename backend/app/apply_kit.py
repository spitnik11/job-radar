"""Application Kit — the structured info every auto-application fills from (spec: gather & organize
all application data). Stored locally in data/apply_kit.local.json (gitignored, treated like a
secret: PII + résumé path). Voluntary EEO fields default to 'Decline to self-identify' and are only
ever what the user explicitly sets — never fabricated."""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel

from .config import DATA_DIR

KIT_FILE = DATA_DIR / "apply_kit.local.json"
DECLINE = "Decline to self-identify"


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
    kit = ApplicationKit(**{**load_kit().model_dump(), **data})   # merge onto existing
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
    if not k.resume_path: need.append("résumé file")
    if k.authorized_us is None: need.append("work authorization")
    return need


def is_ready() -> bool:
    return not missing_fields()

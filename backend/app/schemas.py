"""Pydantic models. CanonicalJob intentionally mirrors Schema.org / Google JobPosting
(spec section 14) so a future public build can re-emit JSON-LD without a rewrite."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

WorkplaceType = Literal["remote", "hybrid", "onsite", "unknown"]
JobStatus = Literal[
    "NEW", "VIEWED", "SAVED", "APPLYING", "APPLIED",
    "PHONE_SCREEN", "INTERVIEW", "FINAL_INTERVIEW", "OFFER",
    "REJECTED", "WITHDRAWN", "DISMISSED", "IGNORED",
]


class CanonicalJob(BaseModel):
    """Normalized job — the common vocabulary every connector produces."""

    id: str                              # stable: "{source_type}:{company_token}:{source_job_id}"
    schema_version: int = 1

    source_type: str                     # greenhouse | lever | ashby | ...
    company_token: str                   # ATS board identifier
    source_job_id: str
    source_url: Optional[str] = None

    title: str
    company_name: str
    company_domain: Optional[str] = None

    description_text: str = ""

    employment_type: Optional[str] = None      # full_time | part_time | contract | ...
    workplace_type: WorkplaceType = "unknown"
    remote: bool = False

    location_name: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None

    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    salary_interval: Optional[str] = None      # year | hour | ...

    date_posted: Optional[datetime] = None
    valid_through: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    apply_url: Optional[str] = None
    canonical_url: Optional[str] = None

    # --- enrichment (filled by the ingestion pipeline / scorer) ---
    detected_skills: list[str] = Field(default_factory=list)
    required_years_min: Optional[int] = None
    required_years_max: Optional[int] = None
    years_required: bool = False               # True = "required", False = "preferred"
    seniority: str = "unknown"

    relevance_score: int = 0
    priority_score: int = 0
    score_breakdown: list["ScoreFactor"] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    suppressed: bool = False
    suppress_reason: Optional[str] = None
    freshness: str = "ACTIVE"

    status: JobStatus = "NEW"


class ScoreFactor(BaseModel):
    factor: str
    got: float          # points awarded
    max: float          # points possible
    detail: str = ""    # human-readable, e.g. "Python, SQL matched; ServiceNow missing"


class ScoreResult(BaseModel):
    relevance: int
    priority: int
    breakdown: list[ScoreFactor]
    flags: list[str] = Field(default_factory=list)
    suppressed: bool = False
    suppress_reason: Optional[str] = None


class CandidateProfile(BaseModel):
    name: str
    years_experience: int
    education_level: str
    education_fields: list[str] = Field(default_factory=list)

    home_city: str
    home_region: str
    home_country: str = "US"

    skills: dict[str, float] = Field(default_factory=dict)
    professional_skills: set[str] = Field(default_factory=set)
    portfolio_skills: set[str] = Field(default_factory=set)
    github_username: Optional[str] = None

    target_roles: list["TargetRole"] = Field(default_factory=list)

    radius_miles: int = 45
    include_remote: bool = True
    include_hybrid: bool = True
    include_onsite: bool = True
    minimum_score: int = 65
    max_required_years: int = 5


class TargetRole(BaseModel):
    title: str
    tier: Literal["A", "B", "C"] = "B"


# --- API output shapes ---

class JobListItem(BaseModel):
    id: str
    title: str
    company_name: str
    workplace_type: WorkplaceType
    remote: bool
    location_name: Optional[str]
    date_posted: Optional[datetime]
    relevance_score: int
    priority_score: int
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    apply_url: Optional[str] = None
    freshness: str = "ACTIVE"
    top_skills: list[str]
    flags: list[str]
    status: JobStatus


class JobDetail(JobListItem):
    description_text: str
    company_domain: Optional[str]
    employment_type: Optional[str]
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: Optional[str]
    salary_interval: Optional[str]
    seniority: str
    detected_skills: list[str]
    score_breakdown: list[ScoreFactor]
    apply_url: Optional[str]
    canonical_url: Optional[str]
    source_type: str


CanonicalJob.model_rebuild()

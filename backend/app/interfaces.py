"""The four architectural seams (spec sections 8, 53-55). Everything else depends on these
Protocols, not on concrete SQLite / httpx / rule-based implementations — so swapping in
Postgres, a new ATS, or an LLM matcher later is a drop-in, not a rewrite."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

import httpx

from .schemas import CandidateProfile, CanonicalJob, ScoreResult


@dataclass
class SourceTarget:
    """One company board to fetch from."""
    connector_id: str
    token: str                       # ATS board identifier
    company_name: str
    company_domain: Optional[str] = None


@dataclass
class RawJob:
    """Untouched payload from a source, before normalization."""
    source_type: str
    source_job_id: str
    company_token: str
    company_name: str
    raw: dict
    company_domain: Optional[str] = None


@dataclass
class VerificationResult:
    verified: bool
    trust_score: int = 100
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class JobConnector(Protocol):
    """Seam 1: a job source. Phase 0 implements fetch + normalize; discover/verify are
    stubs (targets come from companies.yaml, all sources are direct-employer = trust 100)."""
    connector_id: str

    def fetch(self, target: SourceTarget, client: httpx.Client) -> list[RawJob]: ...
    def normalize(self, raw: RawJob) -> CanonicalJob: ...


@runtime_checkable
class JobRepository(Protocol):
    """Seam 2: storage. SQLiteJobRepository now; PostgresJobRepository later."""
    def upsert_many(self, jobs: list[CanonicalJob]) -> int: ...
    def get(self, job_id: str) -> Optional[CanonicalJob]: ...
    def list_jobs(self, **filters) -> list[CanonicalJob]: ...
    def set_status(self, job_id: str, status: str) -> Optional[CanonicalJob]: ...


@runtime_checkable
class MatchEngine(Protocol):
    """Seam 3: scoring. RuleBasedMatchEngine now; Hybrid/LLM later."""
    def score(self, profile: CandidateProfile, job: CanonicalJob) -> ScoreResult: ...


# Seam 4 (the versioned /api/v1 HTTP surface) lives in app/api/v1.py.

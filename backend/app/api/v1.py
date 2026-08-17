"""Versioned HTTP surface (spec section 46). This /api/v1 contract is the stable seam between
the backend and any frontend (this web UI now, Electron later). Breaking changes -> /api/v2."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from .. import APP_VERSION, SCHEMA_VERSION
from ..config import load_profile
from ..db import SessionLocal
from ..ingestion.pipeline import run_ingestion
from ..models import SyncState
from ..repository import SQLiteJobRepository
from ..schemas import CandidateProfile, CanonicalJob, JobDetail, JobListItem

router = APIRouter(prefix="/api/v1")
repo = SQLiteJobRepository()


def _top_skills(job: CanonicalJob, profile: CandidateProfile) -> list[str]:
    owned = [s for s in job.detected_skills if s in profile.skills]
    other = [s for s in job.detected_skills if s not in profile.skills]
    return (owned + other)[:5]


def _list_item(job: CanonicalJob, profile: CandidateProfile) -> JobListItem:
    return JobListItem(
        id=job.id, title=job.title, company_name=job.company_name,
        workplace_type=job.workplace_type, remote=job.remote,
        location_name=job.location_name, date_posted=job.date_posted,
        relevance_score=job.relevance_score, priority_score=job.priority_score,
        top_skills=_top_skills(job, profile), flags=job.flags, status=job.status,
    )


def _detail(job: CanonicalJob, profile: CandidateProfile) -> JobDetail:
    return JobDetail(
        **_list_item(job, profile).model_dump(),
        description_text=job.description_text, company_domain=job.company_domain,
        employment_type=job.employment_type, salary_min=job.salary_min,
        salary_max=job.salary_max, salary_currency=job.salary_currency,
        salary_interval=job.salary_interval, seniority=job.seniority,
        detected_skills=job.detected_skills, score_breakdown=job.score_breakdown,
        apply_url=job.apply_url, canonical_url=job.canonical_url, source_type=job.source_type,
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/version")
def version():
    return {"app_version": APP_VERSION, "schema_version": SCHEMA_VERSION, "api": "v1"}


@router.get("/jobs", response_model=list[JobListItem])
def list_jobs(
    q: Optional[str] = None,
    status: Optional[str] = None,
    remote_only: bool = False,
    min_score: Optional[int] = None,
    include_suppressed: bool = False,
    limit: int = Query(500, le=2000),
):
    profile = load_profile()
    jobs = repo.list_jobs(
        query=q, status=status, remote_only=remote_only,
        min_score=min_score if min_score is not None else profile.minimum_score,
        include_suppressed=include_suppressed, limit=limit,
    )
    return [_list_item(j, profile) for j in jobs]


@router.get("/search", response_model=list[JobListItem])
def search(q: str, limit: int = Query(200, le=2000)):
    return list_jobs(q=q, limit=limit)


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: str):
    job = repo.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.status == "NEW":
        repo.set_status(job_id, "VIEWED")
        job.status = "VIEWED"
    return _detail(job, load_profile())


@router.post("/jobs/{job_id}/save", response_model=JobDetail)
def save_job(job_id: str):
    job = repo.set_status(job_id, "SAVED")
    if job is None:
        raise HTTPException(404, "job not found")
    return _detail(job, load_profile())


@router.post("/jobs/{job_id}/dismiss", response_model=JobDetail)
def dismiss_job(job_id: str):
    job = repo.set_status(job_id, "DISMISSED")
    if job is None:
        raise HTTPException(404, "job not found")
    return _detail(job, load_profile())


@router.post("/jobs/{job_id}/status", response_model=JobDetail)
def set_status(job_id: str, status: str):
    job = repo.set_status(job_id, status)
    if job is None:
        raise HTTPException(404, "job not found")
    return _detail(job, load_profile())


@router.get("/sources")
def sources():
    with SessionLocal() as s:
        rows = s.execute(select(SyncState)).scalars().all()
        return [
            {"connector_id": r.connector_id,
             "last_sync": r.last_sync.isoformat() if r.last_sync else None,
             "jobs_found": r.jobs_found, "status": r.status,
             "failure_count": r.failure_count}
            for r in rows
        ]


@router.post("/sync")
def sync():
    return run_ingestion(repo=repo, profile=load_profile())

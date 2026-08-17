"""Versioned HTTP surface (spec section 46). This /api/v1 contract is the stable seam between
the backend and any frontend (this web UI now, Electron later). Breaking changes -> /api/v2."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

# statuses that count as "in the application pipeline" — the Applied tab shows all of these
PIPELINE = ["APPLYING", "APPLIED", "PHONE_SCREEN", "INTERVIEW", "FINAL_INTERVIEW", "OFFER"]


class NoteIn(BaseModel):
    text: str

from .. import APP_VERSION, SCHEMA_VERSION
from ..config import load_profile
from ..db import SessionLocal
from ..models import SyncState
from ..sync_manager import is_running, start_sync
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
        salary_min=job.salary_min, salary_max=job.salary_max,
        top_skills=_top_skills(job, profile), flags=job.flags, status=job.status,
    )


def _detail(job: CanonicalJob, profile: CandidateProfile) -> JobDetail:
    return JobDetail(
        **_list_item(job, profile).model_dump(),
        description_text=job.description_text, company_domain=job.company_domain,
        employment_type=job.employment_type,          # salary_min/max come via _list_item dump
        salary_currency=job.salary_currency,
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
    status_in: Optional[str] = None,          # CSV; e.g. the Applied tab's pipeline set
    remote_only: bool = False,
    min_score: Optional[int] = None,
    min_salary: Optional[int] = None,
    sort: str = "priority",                   # priority | newest | salary
    include_suppressed: bool = False,
    limit: int = Query(500, le=2000),
):
    profile = load_profile()
    grouped = status_in.split(",") if status_in else None
    scored = None if (status or grouped) else \
        (min_score if min_score is not None else profile.minimum_score)
    jobs = repo.list_jobs(
        query=q, status=status, status_in=grouped, remote_only=remote_only,
        min_score=scored, min_salary=min_salary, sort=sort,
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


@router.get("/jobs/{job_id}/activity")
def activity(job_id: str):
    if repo.get(job_id) is None:
        raise HTTPException(404, "job not found")
    return repo.list_activity(job_id)


@router.post("/jobs/{job_id}/notes")
def add_note(job_id: str, body: NoteIn):
    result = repo.add_note(job_id, body.text)
    if result is None:
        raise HTTPException(404, "job not found")
    return result


@router.get("/pipeline")
def pipeline_statuses():
    return PIPELINE


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
    """Fire-and-forget: kicks the crawl into a background thread and returns immediately."""
    started = start_sync("manual")
    return {"started": started, "running": is_running()}


@router.get("/sync/status")
def sync_status():
    return {"running": is_running()}

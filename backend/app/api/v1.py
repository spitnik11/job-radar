"""Versioned HTTP surface (spec section 46). This /api/v1 contract is the stable seam between
the backend and any frontend (this web UI now, Electron later). Breaking changes -> /api/v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

# statuses that count as "in the application pipeline" — the Applied tab shows all of these
PIPELINE = ["APPLYING", "APPLIED", "PHONE_SCREEN", "INTERVIEW", "FINAL_INTERVIEW", "OFFER"]


class NoteIn(BaseModel):
    text: str


class RerankIn(BaseModel):
    ids: list[str]

from .. import APP_VERSION, SCHEMA_VERSION
from ..config import load_profile, reprocess
from ..db import SessionLocal
from ..github_import import import_github
from ..models import SyncState
from ..sync_manager import is_running, start_sync
from .. import apply_kit, career, email_tracker, geocode, profiles, resume_parser, semantic
from ..streak import state as streak_state
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
        salary_min=job.salary_min, salary_max=job.salary_max, apply_url=job.apply_url,
        freshness=job.freshness, description_snippet=(job.description_text or "")[:420],
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
        canonical_url=job.canonical_url, source_type=job.source_type,   # apply_url via _list_item
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/now")
def now():
    return {"now": datetime.now(timezone.utc).isoformat()}


@router.get("/new_jobs_count")
def new_jobs_count(since: str, min_score: Optional[int] = None):
    """Count of feed-eligible jobs first seen after `since` — drives the 'N new jobs' banner."""
    try:
        dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        return {"count": 0}
    if dt.tzinfo:                                   # DB stores naive UTC — match it
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    floor = min_score if min_score is not None else load_profile().minimum_score
    return {"count": repo.count_new(dt, floor)}


@router.get("/version")
def version():
    return {"app_version": APP_VERSION, "schema_version": SCHEMA_VERSION, "api": "v1"}


@router.get("/jobs", response_model=list[JobListItem])
def list_jobs(
    q: Optional[str] = None,
    status: Optional[str] = None,
    status_in: Optional[str] = None,          # CSV; e.g. the Applied tab's pipeline set
    remote_only: bool = False,
    view: str = "recommended",                # recommended | local | remote
    min_score: Optional[int] = None,
    min_salary: Optional[int] = None,
    employment_type: Optional[str] = None,
    entry_only: bool = False,
    exclude: Optional[str] = None,            # comma-separated words to hide
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
        view=view, geo_enabled=profile.geo_enabled,
        min_score=scored, min_salary=min_salary, sort=sort,
        employment_type=employment_type, entry_only=entry_only,
        exclude=exclude.split(",") if exclude else None,
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


class ProfilePatch(BaseModel):
    name: Optional[str] = None
    data: dict = {}                    # shallow-merged into the profile (nested 'home' merges too)


class LocationIn(BaseModel):
    mode: str = "manual"               # manual | geo
    city: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius_miles: Optional[int] = None


# ---- profiles (save/switch bundles of resume + location + GitHub + prefs) ----

@router.get("/profiles")
def list_profiles():
    return profiles.list_profiles()


@router.get("/profile")
def active_profile():
    pid, data = profiles.get_active()
    return {"id": pid, **data}


@router.post("/profiles")
def create_profile(name: str = "New profile"):
    return {"id": profiles.create(name)}


@router.patch("/profiles/{pid}")
def patch_profile(pid: int, body: ProfilePatch):
    if not profiles.update(pid, body.data, name=body.name):
        raise HTTPException(404, "profile not found")
    reprocess()
    if "home" in body.data:            # location changed -> re-crawl to cover the new area
        start_sync("location-change")
    return {"ok": True}


@router.post("/profiles/{pid}/activate")
def activate_profile(pid: int):
    if not profiles.activate(pid):
        raise HTTPException(404, "profile not found")
    reprocess()
    start_sync("profile-switch")       # new profile may have a different location
    return {"ok": True}


@router.delete("/profiles/{pid}")
def delete_profile(pid: int):
    if not profiles.delete(pid):
        raise HTTPException(400, "cannot delete (not found, or it's the last profile)")
    reprocess()
    return {"ok": True}


@router.post("/profile/location")
def set_location(body: LocationIn):
    """Set the ACTIVE profile's location — geolocation (lat/lon) or manual (city). Manual cities
    are geocoded when possible so the radius works anywhere."""
    pid, _ = profiles.get_active()
    home = {"mode": body.mode}
    if body.mode == "geo" and body.lat is not None and body.lon is not None:
        home.update(lat=body.lat, lon=body.lon, city=body.city or "My location", region=body.region or "")
    else:
        place = ", ".join(x for x in (body.city, body.region) if x)
        coords = geocode.geocode(place) if place else None
        home.update(city=body.city or "", region=body.region or "",
                    lat=coords[0] if coords else None, lon=coords[1] if coords else None)
    patch = {"home": home}
    if body.radius_miles:
        patch["radius_miles"] = body.radius_miles
    profiles.update(pid, patch)
    reprocess()
    start_sync("location-change")
    return {"home": home, "geocoded": home.get("lat") is not None}


@router.post("/profiles/{pid}/resume")
async def upload_resume(pid: int, file: UploadFile = File(...)):
    """Personalize a profile from an uploaded resume — derive skills, years, and education."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty file")
    try:
        parsed = resume_parser.parse_resume(raw, file.filename or "resume")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"could not read resume: {exc}")
    # resume-detected skills become the profile's skills (professional evidence), weighted 0.8
    patch = {
        "skills": {s: 0.8 for s in parsed["skills"]},
        "professional_skills": parsed["skills"],
        "years_experience": parsed["years_experience"],
        "education_level": parsed["education_level"],
        "resume_name": file.filename,
    }
    if not profiles.update(pid, patch):
        raise HTTPException(404, "profile not found")
    reprocess()
    return {"skills": parsed["skills"], "years_experience": parsed["years_experience"],
            "education_level": parsed["education_level"]}


# ---- GitHub evidence (stored on the active profile) ----

@router.get("/profile/github")
def github_profile():
    _, data = profiles.get_active()
    return {"username": data.get("github_username"), "skills": data.get("github_skills", []),
            "repos_scanned": data.get("github_repos", 0)}


@router.post("/profile/github/import")
def github_import_endpoint(username: Optional[str] = None):
    pid, data = profiles.get_active()
    u = username or data.get("github_username")
    if not u:
        raise HTTPException(400, "no GitHub username configured for this profile")
    try:
        result = import_github(u)
    except Exception as exc:  # noqa: BLE001 — surface a clean error to the UI
        raise HTTPException(502, f"GitHub import failed: {exc}")
    profiles.update(pid, {"github_username": u, "github_skills": result["skills"],
                          "github_repos": result["repos_scanned"]})
    reprocess()
    return {"username": result["username"], "repos_scanned": result["repos_scanned"],
            "skills": result["skills"]}


@router.get("/email/status")
def email_status():
    return {"enabled": email_tracker.creds() is not None}


@router.post("/email/check")
def email_check():
    """Poll the mailbox once (manual trigger). Inert unless IMAP creds are configured."""
    return email_tracker.check()


@router.get("/career/report")
def career_report():
    return career.report()


# ---- Auto-apply: Application Kit + queue (Phase 0; no browser/submitting yet) ----

class KitIn(BaseModel):
    data: dict


@router.get("/apply/kit")
def get_kit():
    return apply_kit.load_kit().model_dump()


@router.put("/apply/kit")
def put_kit(body: KitIn):
    apply_kit.save_kit(body.data)
    return {"ready": apply_kit.is_ready(), "missing": apply_kit.missing_fields()}


@router.get("/apply/queue", response_model=list[JobListItem])
def apply_queue():
    profile = load_profile()
    return [_list_item(j, profile) for j in repo.list_jobs(status="AUTO_QUEUED", limit=999)]


@router.post("/jobs/{job_id}/queue", response_model=JobDetail)
def queue_job(job_id: str):
    job = repo.set_status(job_id, "AUTO_QUEUED")
    if job is None:
        raise HTTPException(404, "job not found")
    return _detail(job, load_profile())


@router.get("/apply/status")
def apply_status():
    return {
        "queued": len(repo.list_jobs(status="AUTO_QUEUED", limit=999)),
        "applied": repo.count_applications(),
        "kit_ready": apply_kit.is_ready(),
        "kit_missing": apply_kit.missing_fields(),
    }


@router.post("/apply/dryrun/{job_id:path}")
def apply_dryrun(job_id: str):
    """Open the job's apply page, read the form, and preview what the kit would fill — NO submit.
    Sync (Playwright) endpoint: FastAPI runs it in a threadpool."""
    job = repo.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not apply_kit.is_ready():
        raise HTTPException(400, {"error": "kit incomplete", "missing": apply_kit.missing_fields()})
    from ..apply import engine as apply_engine
    return apply_engine.dry_run({"id": job.id, "apply_url": job.apply_url,
                                 "title": job.title, "company_name": job.company_name})


@router.post("/apply/prepare/{job_id:path}")
def apply_prepare(job_id: str):
    """Actually fill the job's live form, read back every required field's state, and report whether
    it's submission-ready plus every blocker that would stop it. Never clicks Submit — the real
    submission is a human action. Sync (Playwright) endpoint; runs in a threadpool."""
    job = repo.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not apply_kit.is_ready():
        raise HTTPException(400, {"error": "kit incomplete", "missing": apply_kit.missing_fields()})
    from ..apply import engine as apply_engine
    return apply_engine.prepare({"id": job.id, "apply_url": job.apply_url,
                                 "title": job.title, "company_name": job.company_name})


@router.get("/apply/shot/{job_id:path}")
def apply_shot(job_id: str):
    from ..apply.engine import shot_path
    path = shot_path(job_id)
    if not path.is_file():
        raise HTTPException(404, "no screenshot")
    return FileResponse(str(path), media_type="image/png")


@router.get("/streak")
def streak():
    """Application milestone/streak (0 tier = greyed fire; progress is toward the next milestone)."""
    return streak_state(repo.count_applications())


@router.get("/semantic/status")
def semantic_status():
    return {"enabled": semantic.enabled()}


@router.post("/rerank")
def rerank(body: RerankIn):
    """Reorder the given job ids by blended (deterministic + semantic) score. No-op if disabled."""
    if not semantic.enabled():
        return {"order": body.ids, "scores": {}}
    items = []
    for jid in body.ids[:80]:                       # cap the work per request
        j = repo.get(jid)
        if j:
            items.append({"id": jid, "relevance": j.relevance_score,
                          "text": f"{j.title}. {(j.description_text or '')[:500]}"})
    return semantic.rerank(items, load_profile())


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

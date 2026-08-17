"""SQLiteJobRepository — the only place business logic touches SQLite (spec section 53)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_, select

from .db import SessionLocal
from .models import Job, JobEvent, JobNote
from .schemas import CanonicalJob, ScoreFactor

# Statuses the user owns — never overwritten by a re-sync.
USER_OWNED = {
    "SAVED", "APPLYING", "APPLIED", "PHONE_SCREEN", "INTERVIEW",
    "FINAL_INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN", "DISMISSED", "IGNORED",
}

_SCALAR_FIELDS = [
    "source_type", "company_token", "source_job_id", "source_url",
    "title", "company_name", "company_domain", "description_text",
    "employment_type", "workplace_type", "remote",
    "location_name", "city", "region", "country",
    "salary_min", "salary_max", "salary_currency", "salary_interval",
    "date_posted", "valid_through", "apply_url", "canonical_url",
    "required_years_min", "required_years_max", "years_required", "seniority",
    "relevance_score", "priority_score", "suppressed", "suppress_reason",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_canonical(row: Job) -> CanonicalJob:
    return CanonicalJob(
        id=row.id,
        source_type=row.source_type,
        company_token=row.company_token,
        source_job_id=row.source_job_id,
        source_url=row.source_url,
        title=row.title,
        company_name=row.company_name,
        company_domain=row.company_domain,
        description_text=row.description_text or "",
        employment_type=row.employment_type,
        workplace_type=row.workplace_type,
        remote=row.remote,
        location_name=row.location_name,
        city=row.city,
        region=row.region,
        country=row.country,
        salary_min=row.salary_min,
        salary_max=row.salary_max,
        salary_currency=row.salary_currency,
        salary_interval=row.salary_interval,
        date_posted=row.date_posted,
        valid_through=row.valid_through,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        apply_url=row.apply_url,
        canonical_url=row.canonical_url,
        detected_skills=row.detected_skills or [],
        required_years_min=row.required_years_min,
        required_years_max=row.required_years_max,
        years_required=row.years_required,
        seniority=row.seniority,
        relevance_score=row.relevance_score,
        priority_score=row.priority_score,
        score_breakdown=[ScoreFactor(**f) for f in (row.score_breakdown or [])],
        flags=row.flags or [],
        suppressed=row.suppressed,
        suppress_reason=row.suppress_reason,
        status=row.status,
    )


class SQLiteJobRepository:
    def upsert_many(self, jobs: list[CanonicalJob]) -> int:
        now = _now()
        n = 0
        with SessionLocal() as s:
            for job in jobs:
                row = s.get(Job, job.id)
                if row is None:
                    row = Job(id=job.id, first_seen_at=now, status=job.status)
                    s.add(row)
                for f in _SCALAR_FIELDS:
                    setattr(row, f, getattr(job, f))
                row.detected_skills = job.detected_skills
                row.flags = job.flags
                row.score_breakdown = [f.model_dump() for f in job.score_breakdown]
                row.last_seen_at = now
                if row.status not in USER_OWNED:      # preserve the user's decisions
                    row.status = job.status
                n += 1
            s.commit()
        return n

    def get(self, job_id: str) -> Optional[CanonicalJob]:
        with SessionLocal() as s:
            row = s.get(Job, job_id)
            return _to_canonical(row) if row else None

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        status_in: Optional[list[str]] = None,
        include_suppressed: bool = False,
        include_dismissed: bool = False,
        min_score: Optional[int] = None,
        remote_only: bool = False,
        query: Optional[str] = None,
        limit: int = 500,
    ) -> list[CanonicalJob]:
        stmt = select(Job)
        if status:
            stmt = stmt.where(Job.status == status)
        elif status_in:
            stmt = stmt.where(Job.status.in_(status_in))
        else:
            if not include_suppressed:
                stmt = stmt.where(Job.suppressed.is_(False))
            if not include_dismissed:
                stmt = stmt.where(Job.status.notin_(["DISMISSED", "IGNORED"]))
        if min_score is not None:
            stmt = stmt.where(Job.relevance_score >= min_score)
        if remote_only:
            stmt = stmt.where(Job.remote.is_(True))
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(
                    Job.title.ilike(like),
                    Job.company_name.ilike(like),
                    Job.description_text.ilike(like),
                )
            )
        stmt = stmt.order_by(Job.priority_score.desc(), Job.relevance_score.desc()).limit(limit)
        with SessionLocal() as s:
            return [_to_canonical(r) for r in s.execute(stmt).scalars()]

    def set_status(self, job_id: str, status: str) -> Optional[CanonicalJob]:
        with SessionLocal() as s:
            row = s.get(Job, job_id)
            if row is None:
                return None
            old = row.status
            row.status = status
            # log meaningful transitions only (skip the VIEWED "undo"/just-looked state)
            if status != old and status != "VIEWED":
                s.add(JobEvent(job_id=job_id, created_at=_now(), kind="status",
                               detail=f"{old} → {status}"))
            s.commit()
            return _to_canonical(row)

    def add_note(self, job_id: str, text: str) -> Optional[list[dict]]:
        text = (text or "").strip()
        with SessionLocal() as s:
            if s.get(Job, job_id) is None:
                return None
            if text:
                s.add(JobNote(job_id=job_id, created_at=_now(), text=text))
                s.commit()
        return self.list_activity(job_id)

    def list_activity(self, job_id: str) -> list[dict]:
        """Merged newest-first timeline of notes + status events."""
        with SessionLocal() as s:
            notes = s.execute(select(JobNote).where(JobNote.job_id == job_id)).scalars().all()
            events = s.execute(select(JobEvent).where(JobEvent.job_id == job_id)).scalars().all()
        items = [{"id": n.id, "ts": n.created_at.isoformat(), "kind": "note", "text": n.text}
                 for n in notes]
        items += [{"ts": e.created_at.isoformat(), "kind": e.kind, "text": e.detail}
                  for e in events]
        items.sort(key=lambda x: x["ts"], reverse=True)
        return items

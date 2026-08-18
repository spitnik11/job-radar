"""SQLAlchemy 2.0 ORM. Phase-0-minimal tables — a jobs table sufficient to hold a
CanonicalJob plus user status/scores, a companies registry, and metadata for
schema-version stamping (so Alembic gets a clean baseline at the first real migration)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_type: Mapped[str] = mapped_column(String, index=True)
    company_token: Mapped[str] = mapped_column(String, index=True)
    source_job_id: Mapped[str] = mapped_column(String)
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    title: Mapped[str] = mapped_column(String, index=True)
    company_name: Mapped[str] = mapped_column(String, index=True)
    company_domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description_text: Mapped[str] = mapped_column(Text, default="")

    employment_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    workplace_type: Mapped[str] = mapped_column(String, default="unknown")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)

    location_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    salary_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salary_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    salary_interval: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    date_posted: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_through: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    apply_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    canonical_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    detected_skills: Mapped[list] = mapped_column(JSON, default=list)
    required_years_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    required_years_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    years_required: Mapped[bool] = mapped_column(Boolean, default=False)
    seniority: Mapped[str] = mapped_column(String, default="unknown")

    relevance_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    priority_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_breakdown: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    suppress_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # ACTIVE = seen in the latest sync of its board; EXPIRED = board synced OK but posting gone (spec s.28)
    freshness: Mapped[str] = mapped_column(String, default="ACTIVE", index=True)

    status: Mapped[str] = mapped_column(String, default="NEW", index=True)


class JobNote(Base):
    """Free-text note the user attaches to a job (spec section 29)."""
    __tablename__ = "job_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    text: Mapped[str] = mapped_column(Text)


class JobEvent(Base):
    """Timeline entry — mostly auto-logged status changes (spec section 29)."""
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String, default="status")
    detail: Mapped[str] = mapped_column(String, default="")


class SchemaMeta(Base):
    __tablename__ = "schema_metadata"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class SyncState(Base):
    """Per-connector health (spec section 45)."""
    __tablename__ = "source_sync_state"
    connector_id: Mapped[str] = mapped_column(String, primary_key=True)
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="ok")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

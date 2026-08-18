"""Saveable/switchable candidate profiles. Each profile bundles resume-derived skills, location,
GitHub evidence, and search preferences. One profile is active; load_profile() builds a
CandidateProfile from it. The first run seeds a 'Default' profile from the checked-in YAML."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy import update as sql_update

from .db import ENGINE, SessionLocal
from .models import Base, Profile
from .schemas import CandidateProfile, TargetRole

_tables_ready = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_data() -> dict:
    """The original single-user defaults, from profile.yaml + settings.yaml."""
    from .config import _load_yaml
    p, s = _load_yaml("profile.yaml"), _load_yaml("settings.yaml")
    cand, home, search = p.get("candidate", {}), p.get("home", {}), s.get("search", {})
    return {
        "name": cand.get("name", "Candidate"),
        "years_experience": cand.get("years_experience", 0),
        "education_level": cand.get("education", {}).get("level", "unknown"),
        "education_fields": cand.get("education", {}).get("fields", []),
        "home": {"mode": "manual", "city": home.get("city", ""), "region": home.get("region", ""),
                 "country": home.get("country", "US"), "lat": None, "lon": None},
        "radius_miles": search.get("radius_miles", 45),
        "include_remote": search.get("include_remote", True),
        "include_hybrid": search.get("include_hybrid", True),
        "include_onsite": search.get("include_onsite", True),
        "minimum_score": search.get("minimum_score", 65),
        "max_required_years": search.get("max_required_years", 5),
        "skills": p.get("skills", {}),
        "professional_skills": p.get("professional_skills", []),
        "portfolio_skills": p.get("portfolio_skills", []),
        "target_roles": s.get("target_roles", []),
        "github_username": p.get("github", {}).get("username"),
        "github_skills": [],
        "resume_name": None,
    }


def _ensure_seed() -> None:
    global _tables_ready
    if not _tables_ready:
        Base.metadata.create_all(ENGINE)      # idempotent — profiles table exists even before init_db
        _tables_ready = True
    with SessionLocal() as s:
        if s.execute(select(Profile.id).limit(1)).first() is None:
            s.add(Profile(name="Default", active=True, data=_default_data(), updated_at=_now()))
            s.commit()


def list_profiles() -> list[dict]:
    _ensure_seed()
    with SessionLocal() as s:
        rows = s.execute(select(Profile).order_by(Profile.id)).scalars().all()
        return [{"id": r.id, "name": r.name, "active": r.active,
                 "home": r.data.get("home", {}), "resume_name": r.data.get("resume_name"),
                 "skills_count": len(r.data.get("skills", {}))} for r in rows]


def get_active() -> tuple[int, dict]:
    _ensure_seed()
    with SessionLocal() as s:
        r = s.execute(select(Profile).where(Profile.active.is_(True))).scalars().first()
        if r is None:
            r = s.execute(select(Profile).order_by(Profile.id)).scalars().first()
        return r.id, dict(r.data)


def get_active_data() -> dict:
    return get_active()[1]


def create(name: str, data: Optional[dict] = None) -> int:
    with SessionLocal() as s:
        row = Profile(name=name, active=False, data=data or _default_data(), updated_at=_now())
        s.add(row)
        s.commit()
        return row.id


def update(pid: int, patch: dict, name: Optional[str] = None) -> bool:
    """Shallow-merge `patch` into the profile's data (nested 'home' merges one level deep)."""
    with SessionLocal() as s:
        r = s.get(Profile, pid)
        if r is None:
            return False
        d = dict(r.data)
        for k, v in patch.items():
            if k == "home" and isinstance(v, dict):
                d["home"] = {**d.get("home", {}), **v}
            else:
                d[k] = v
        r.data = d
        if name:
            r.name = name
        r.updated_at = _now()
        s.commit()
        return True


def activate(pid: int) -> bool:
    with SessionLocal() as s:
        if s.get(Profile, pid) is None:
            return False
        s.execute(sql_update(Profile).values(active=False))
        s.get(Profile, pid).active = True
        s.commit()
        return True


def delete(pid: int) -> bool:
    with SessionLocal() as s:
        r = s.get(Profile, pid)
        if r is None or s.execute(select(Profile.id)).all().__len__() <= 1:
            return False                      # never delete the last profile
        was_active = r.active
        s.delete(r)
        s.commit()
        if was_active:
            first = s.execute(select(Profile).order_by(Profile.id)).scalars().first()
            first.active = True
            s.commit()
        return True


def build_candidate(data: dict) -> CandidateProfile:
    home = data.get("home", {})
    skills = dict(data.get("skills", {}))
    portfolio = set(data.get("portfolio_skills", []))
    for sk in data.get("github_skills", []):          # GitHub evidence -> portfolio-proven
        portfolio.add(sk)
        skills.setdefault(sk, 0.6)
    return CandidateProfile(
        name=data.get("name", "Candidate"),
        years_experience=data.get("years_experience", 0),
        education_level=data.get("education_level", "unknown"),
        education_fields=data.get("education_fields", []),
        home_city=home.get("city", ""), home_region=home.get("region", ""),
        home_country=home.get("country", "US"),
        home_lat=home.get("lat"), home_lon=home.get("lon"), home_mode=home.get("mode", "manual"),
        skills=skills, professional_skills=set(data.get("professional_skills", [])),
        portfolio_skills=portfolio, github_username=data.get("github_username"),
        target_roles=[TargetRole(**r) for r in data.get("target_roles", [])],
        radius_miles=data.get("radius_miles", 45),
        include_remote=data.get("include_remote", True),
        include_hybrid=data.get("include_hybrid", True),
        include_onsite=data.get("include_onsite", True),
        minimum_score=data.get("minimum_score", 65),
        max_required_years=data.get("max_required_years", 5),
    )

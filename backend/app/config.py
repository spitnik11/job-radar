"""Load the candidate profile + search settings + seed companies from data/*.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .interfaces import SourceTarget
from .schemas import CandidateProfile, TargetRole

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_yaml(name: str) -> dict:
    with open(DATA_DIR / name, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def load_profile() -> CandidateProfile:
    p = _load_yaml("profile.yaml")
    s = _load_yaml("settings.yaml")
    cand = p.get("candidate", {})
    home = p.get("home", {})
    search = s.get("search", {})

    return CandidateProfile(
        name=cand.get("name", "Candidate"),
        years_experience=cand.get("years_experience", 0),
        education_level=cand.get("education", {}).get("level", "unknown"),
        education_fields=cand.get("education", {}).get("fields", []),
        home_city=home.get("city", ""),
        home_region=home.get("region", ""),
        home_country=home.get("country", "US"),
        skills=p.get("skills", {}),
        professional_skills=set(p.get("professional_skills", [])),
        portfolio_skills=set(p.get("portfolio_skills", [])),
        target_roles=[TargetRole(**r) for r in s.get("target_roles", [])],
        radius_miles=search.get("radius_miles", 45),
        include_remote=search.get("include_remote", True),
        include_hybrid=search.get("include_hybrid", True),
        include_onsite=search.get("include_onsite", True),
        minimum_score=search.get("minimum_score", 65),
        max_required_years=search.get("max_required_years", 5),
    )


@lru_cache(maxsize=1)
def load_targets() -> list[SourceTarget]:
    """Flatten companies.yaml into per-connector fetch targets, honoring enabled sources."""
    companies = _load_yaml("companies.yaml")
    enabled = _load_yaml("settings.yaml").get("sources", {})
    targets: list[SourceTarget] = []
    for connector_id, entries in companies.items():
        if not enabled.get(connector_id, True):
            continue
        for e in entries or []:
            targets.append(
                SourceTarget(
                    connector_id=connector_id,
                    token=e["token"],
                    company_name=e.get("name", e["token"]),
                    company_domain=e.get("domain"),
                )
            )
    return targets

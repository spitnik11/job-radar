"""USAJOBS Search API (spec section 9) — the official federal jobs feed. Strong fit for a Tampa
candidate (MacDill AFB, SOCOM/CENTCOM, the VA hire IT support heavily, entry-level, native radius).

Unlike the ATS connectors this one is *query*-driven, not company-scoped: each companies.yaml
`usajobs:` entry's `token` is a search keyword. Location + radius come from the profile.

Requires a FREE key (https://developer.usajobs.gov/apirequest/) — provide via env vars
USAJOBS_API_KEY + USAJOBS_EMAIL, or backend/data/secrets.local.yaml (gitignored). No key => the
connector is inert (returns nothing) instead of erroring.
"""

from __future__ import annotations

import httpx

from ..config import load_profile, load_usajobs_creds
from ..interfaces import RawJob, SourceTarget
from ..schemas import CanonicalJob
from .base import REQUEST_TIMEOUT, norm_employment, parse_dt, strip_html

SEARCH_URL = "https://data.usajobs.gov/api/search"
_warned = False


class UsaJobsConnector:
    connector_id = "usajobs"

    def fetch(self, target: SourceTarget, client: httpx.Client) -> list[RawJob]:
        global _warned
        api_key, email = load_usajobs_creds()
        if not api_key or not email:
            if not _warned:
                print("[usajobs] no API key — skipping (set USAJOBS_API_KEY + USAJOBS_EMAIL, "
                      "or backend/data/secrets.local.yaml). Free key: developer.usajobs.gov")
                _warned = True
            return []

        profile = load_profile()
        params = {
            "Keyword": target.token,
            "LocationName": f"{profile.home_city}, {profile.home_region}",
            "Radius": str(profile.radius_miles),
            "ResultsPerPage": "100",
            "Fields": "Min",
        }
        headers = {"Authorization-Key": api_key, "User-Agent": email, "Host": "data.usajobs.gov"}
        r = client.get(SEARCH_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        items = r.json().get("SearchResult", {}).get("SearchResultItems", [])
        return [
            RawJob(
                source_type=self.connector_id,
                source_job_id=str(it.get("MatchedObjectId")),
                company_token="federal",
                company_name="USAJOBS",
                raw=it.get("MatchedObjectDescriptor", {}),
            )
            for it in items
        ]

    def normalize(self, raw: RawJob) -> CanonicalJob:
        d = raw.raw
        details = (d.get("UserArea") or {}).get("Details") or {}
        loc = (d.get("PositionLocation") or [{}])[0]
        loc_display = d.get("PositionLocationDisplay") or loc.get("LocationName") or ""
        remote = bool(details.get("RemoteIndicator")) or "remote" in loc_display.lower()

        desc = details.get("JobSummary") or ""
        if not desc:
            duties = details.get("MajorDutiesList") or []
            desc = "\n".join(duties) if isinstance(duties, list) else str(duties)
        desc = strip_html(desc)
        if details.get("QualificationSummary"):
            desc += "\n\nQualifications: " + strip_html(details["QualificationSummary"])

        rem = (d.get("PositionRemuneration") or [{}])[0]
        interval = {"Per Year": "year", "Per Hour": "hour"}.get(rem.get("RateIntervalCode"))
        sched = (d.get("PositionSchedule") or [{}])[0].get("Name")
        apply_uri = d.get("ApplyURI") or []

        return CanonicalJob(
            id=f"usajobs:federal:{raw.source_job_id}",
            source_type=self.connector_id,
            company_token="federal",
            source_job_id=raw.source_job_id,
            source_url=d.get("PositionURI"),
            title=(d.get("PositionTitle") or "").strip(),
            company_name=d.get("OrganizationName") or d.get("DepartmentName") or "Federal Government",
            description_text=desc,
            employment_type=norm_employment(sched),
            workplace_type="remote" if remote else "onsite",
            remote=remote,
            location_name=loc_display or None,
            city=(loc.get("CityName") or "").split(",")[0] or None,
            region=loc.get("CountrySubDivisionCode"),
            country="US",
            salary_min=_num(rem.get("MinimumRange")),
            salary_max=_num(rem.get("MaximumRange")),
            salary_currency="USD" if rem.get("MinimumRange") else None,
            salary_interval=interval,
            date_posted=parse_dt(d.get("PublicationStartDate")),
            valid_through=parse_dt(d.get("ApplicationCloseDate")),
            apply_url=apply_uri[0] if apply_uri else d.get("PositionURI"),
            canonical_url=d.get("PositionURI"),
        )


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None

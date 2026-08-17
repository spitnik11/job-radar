"""Greenhouse Job Board API — public JSON, no auth (spec section 9).
GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
"""

from __future__ import annotations

import httpx

from ..interfaces import RawJob, SourceTarget
from ..schemas import CanonicalJob
from .base import REQUEST_TIMEOUT, USER_AGENT, infer_workplace, parse_dt, strip_html

BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


class GreenhouseConnector:
    connector_id = "greenhouse"

    def fetch(self, target: SourceTarget, client: httpx.Client) -> list[RawJob]:
        r = client.get(BASE.format(token=target.token),
                       timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        return [
            RawJob(
                source_type=self.connector_id,
                source_job_id=str(j.get("id")),
                company_token=target.token,
                company_name=target.company_name,
                company_domain=target.company_domain,
                raw=j,
            )
            for j in r.json().get("jobs", [])
        ]

    def normalize(self, raw: RawJob) -> CanonicalJob:
        j = raw.raw
        location = (j.get("location") or {}).get("name") or ""
        workplace, remote = infer_workplace(location)
        url = j.get("absolute_url")
        return CanonicalJob(
            id=f"{self.connector_id}:{raw.company_token}:{raw.source_job_id}",
            source_type=self.connector_id,
            company_token=raw.company_token,
            source_job_id=raw.source_job_id,
            source_url=url,
            title=j.get("title", "").strip(),
            company_name=raw.company_name,
            company_domain=raw.company_domain,
            description_text=strip_html(j.get("content")),
            workplace_type=workplace,
            remote=remote,
            location_name=location or None,
            date_posted=parse_dt(j.get("updated_at")),
            apply_url=url,
            canonical_url=url,
        )

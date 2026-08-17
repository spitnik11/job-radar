"""Ashby public Job Posting API (spec section 9).
GET https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true
"""

from __future__ import annotations

import httpx

from ..interfaces import RawJob, SourceTarget
from ..schemas import CanonicalJob
from .base import (REQUEST_TIMEOUT, USER_AGENT, infer_workplace, norm_employment,
                   parse_dt, strip_html)

BASE = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"


class AshbyConnector:
    connector_id = "ashby"

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
        location = j.get("location") or ""
        workplace, remote = infer_workplace(location, explicit_remote=j.get("isRemote"))
        return CanonicalJob(
            id=f"{self.connector_id}:{raw.company_token}:{raw.source_job_id}",
            source_type=self.connector_id,
            company_token=raw.company_token,
            source_job_id=raw.source_job_id,
            source_url=j.get("jobUrl"),
            title=(j.get("title") or "").strip(),
            company_name=raw.company_name,
            company_domain=raw.company_domain,
            description_text=j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")),
            employment_type=norm_employment(j.get("employmentType")),
            workplace_type=workplace,
            remote=remote,
            location_name=location or None,
            date_posted=parse_dt(j.get("publishedAt")),
            apply_url=j.get("applyUrl") or j.get("jobUrl"),
            canonical_url=j.get("jobUrl"),
        )

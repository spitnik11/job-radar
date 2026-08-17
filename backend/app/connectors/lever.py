"""Lever Postings API — public JSON (spec section 9).
GET https://api.lever.co/v0/postings/{token}?mode=json
"""

from __future__ import annotations

import httpx

from ..interfaces import RawJob, SourceTarget
from ..schemas import CanonicalJob
from .base import (REQUEST_TIMEOUT, USER_AGENT, infer_workplace, norm_employment,
                   parse_dt, strip_html)

BASE = "https://api.lever.co/v0/postings/{token}?mode=json"

_WORKPLACE = {"remote": ("remote", True), "on-site": ("onsite", False),
              "onsite": ("onsite", False), "hybrid": ("hybrid", False)}


class LeverConnector:
    connector_id = "lever"

    def fetch(self, target: SourceTarget, client: httpx.Client) -> list[RawJob]:
        r = client.get(BASE.format(token=target.token),
                       timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        return [
            RawJob(
                source_type=self.connector_id,
                source_job_id=str(p.get("id")),
                company_token=target.token,
                company_name=target.company_name,
                company_domain=target.company_domain,
                raw=p,
            )
            for p in r.json()
        ]

    def normalize(self, raw: RawJob) -> CanonicalJob:
        p = raw.raw
        cats = p.get("categories") or {}
        location = cats.get("location") or ""
        wt = (p.get("workplaceType") or "").lower()
        workplace, remote = _WORKPLACE.get(wt, infer_workplace(location))

        salary = p.get("salaryRange") or {}
        return CanonicalJob(
            id=f"{self.connector_id}:{raw.company_token}:{raw.source_job_id}",
            source_type=self.connector_id,
            company_token=raw.company_token,
            source_job_id=raw.source_job_id,
            source_url=p.get("hostedUrl"),
            title=(p.get("text") or "").strip(),
            company_name=raw.company_name,
            company_domain=raw.company_domain,
            description_text=p.get("descriptionPlain") or strip_html(p.get("description")),
            employment_type=norm_employment(cats.get("commitment")),
            workplace_type=workplace,
            remote=remote,
            location_name=location or None,
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            salary_currency=salary.get("currency"),
            salary_interval=(salary.get("interval") or "").replace("per-", "") or None,
            date_posted=parse_dt(p.get("createdAt")),
            apply_url=p.get("applyUrl") or p.get("hostedUrl"),
            canonical_url=p.get("hostedUrl"),
        )

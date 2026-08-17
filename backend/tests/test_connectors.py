"""Fixture-based connector tests (spec section 59) — never hit live endpoints in tests."""

from app.connectors.ashby import AshbyConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.interfaces import RawJob


def _raw(source, token, jid, payload):
    return RawJob(source_type=source, source_job_id=jid, company_token=token,
                  company_name="Acme", raw=payload)


def test_greenhouse_normalize():
    payload = {
        "id": 123, "title": "Application Support Analyst",
        "updated_at": "2026-08-15T10:00:00-04:00",
        "location": {"name": "Remote - US"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
        "content": "&lt;p&gt;Support our apps with &lt;b&gt;Python&lt;/b&gt; and SQL.&lt;/p&gt;",
    }
    job = GreenhouseConnector().normalize(_raw("greenhouse", "acme", "123", payload))
    assert job.id == "greenhouse:acme:123"
    assert job.title == "Application Support Analyst"
    assert job.remote is True and job.workplace_type == "remote"
    assert "Python" in job.description_text and "<b>" not in job.description_text
    assert job.apply_url.endswith("/123")
    assert job.date_posted is not None


def test_lever_normalize():
    payload = {
        "id": "abc", "text": "Full Stack Developer",
        "categories": {"location": "Tampa, FL", "commitment": "Full-time"},
        "descriptionPlain": "Build with React and Node.",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "applyUrl": "https://jobs.lever.co/acme/abc/apply",
        "workplaceType": "hybrid", "createdAt": 1723700000000,
    }
    job = LeverConnector().normalize(_raw("lever", "acme", "abc", payload))
    assert job.id == "lever:acme:abc"
    assert job.workplace_type == "hybrid" and job.remote is False
    assert job.employment_type == "full_time"
    assert job.location_name == "Tampa, FL"
    assert job.apply_url.endswith("/apply")


def test_ashby_normalize():
    payload = {
        "id": "z9", "title": "QA Analyst", "location": "Remote, US", "isRemote": True,
        "employmentType": "FullTime", "descriptionPlain": "Test with Selenium and SQL.",
        "jobUrl": "https://jobs.ashbyhq.com/acme/z9", "applyUrl": "https://jobs.ashbyhq.com/acme/z9/apply",
        "publishedAt": "2026-08-10T00:00:00.000Z",
    }
    job = AshbyConnector().normalize(_raw("ashby", "acme", "z9", payload))
    assert job.id == "ashby:acme:z9"
    assert job.remote is True and job.employment_type == "full_time"
    assert job.date_posted is not None

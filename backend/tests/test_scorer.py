"""Known-case scoring (spec section 59). Thresholds are calibrated to THIS scorer; the
invariants that matter are the ordering and that off-target jobs fall below minimum_score."""

from app.config import load_profile
from app.ingestion.pipeline import _enrich
from app.matching.scorer import RuleBasedMatchEngine
from app.schemas import CanonicalJob

PROFILE = load_profile()
ENGINE = RuleBasedMatchEngine()


def _job(title, desc, *, remote=False, workplace="onsite", location="Tampa, FL", posted=None):
    from datetime import datetime, timezone
    j = CanonicalJob(
        id=f"test:x:{title}", source_type="test", company_token="x", source_job_id=title,
        title=title, company_name="Acme", description_text=desc,
        remote=remote, workplace_type=workplace, location_name=location,
        date_posted=posted or datetime.now(timezone.utc),
    )
    _enrich(j)
    return j, ENGINE.score(PROFILE, j)


def test_strong_fit_scores_high():
    _, r = _job(
        "Application Support Analyst",
        "Support our internal apps. Python and SQL scripting, Microsoft 365 administration, "
        "Active Directory, troubleshooting, and customer service. Bachelor's degree; "
        "2 years of support experience preferred.",
        remote=True, workplace="remote",
    )
    assert r.relevance >= 80


def test_ordering_strong_gt_adjacent_gt_unrelated():
    _, strong = _job(
        "IT Support Specialist",
        "Windows, Microsoft 365, Active Directory, troubleshooting, hardware support, "
        "customer service. Bachelor's preferred.",
        remote=True, workplace="remote",
    )
    _, adjacent = _job(
        "Data Analyst",
        "Build dashboards with SQL, Tableau and Power BI. 3 years of analytics experience required.",
    )
    _, unrelated = _job(
        "Registered Nurse",
        "Provide bedside patient care in our Tampa clinic. Nursing license required.",
    )
    assert strong.relevance > adjacent.relevance > unrelated.relevance
    assert unrelated.relevance < PROFILE.minimum_score   # off-target => filtered by default


def test_senior_title_is_suppressed():
    job, _ = _job(
        "Staff Application Support Analyst",
        "Python, SQL, Microsoft 365. 8 years of experience required.",
        remote=True, workplace="remote",
    )
    assert job.suppressed is True


def test_missing_skills_lower_than_full_match():
    _, full = _job("Python Developer",
                   "Python, JavaScript, React, SQL, REST API. Remote.", remote=True, workplace="remote")
    _, partial = _job("Python Developer",
                      "Python plus heavy Java, C#, .NET, AWS, Kubernetes and Salesforce.",
                      remote=True, workplace="remote")
    assert full.relevance > partial.relevance

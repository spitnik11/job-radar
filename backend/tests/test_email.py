"""Email classifier + matcher — pure logic, no mailbox (spec: multi-signal, never sender alone)."""

from app import email_tracker as et
from app.schemas import CanonicalJob


def _job(**kw):
    base = dict(id="e:x:1", source_type="t", company_token="x", source_job_id="1",
                title="Software Engineer", company_name="Acme Corp", company_domain="acme.com")
    base.update(kw)
    return CanonicalJob(**base)


def test_classify_offer_needs_multiple_signals():
    s, c = et.classify("Your offer from Acme", "We are pleased to offer you the position. Offer letter attached.")
    assert s == "OFFER" and c >= 3


def test_classify_rejection():
    s, _ = et.classify("Update on your application",
                       "Unfortunately we will not be moving forward. We decided to pursue other candidates.")
    assert s == "REJECTED"


def test_classify_ambiguous_returns_none():
    # a single weak keyword must NOT trigger a decision
    assert et.classify("Re: your application", "Thanks, we'll be in touch.")[0] is None


def test_match_uses_company_and_title_not_sender_alone():
    jobs = [_job(), _job(id="e:y:2", title="Data Analyst", company_name="Beta Inc", company_domain="beta.io")]
    # sender is a generic recruiting address, but company + title appear in the body
    m = et.match_email("noreply@greenhouse.io", "Acme Corp — Software Engineer",
                       "Thank you for applying to the Software Engineer role at Acme Corp.", jobs)
    assert m is not None and m.company_name == "Acme Corp"


def test_match_none_when_no_signals():
    jobs = [_job()]
    assert et.match_email("random@x.com", "Newsletter", "Weekly deals just for you", jobs) is None

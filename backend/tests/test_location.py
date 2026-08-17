"""Location / radius filtering (spec section 7). hard_fail=True means drop before storing."""

from app.config import load_profile
from app.matching import location as loc
from app.schemas import CanonicalJob

PROFILE = load_profile()   # Brandon FL, 45 mi, remote+hybrid+onsite on


def _job(**kw):
    base = dict(id="t:x:1", source_type="t", company_token="x", source_job_id="1",
                title="Dev", company_name="Acme")
    base.update(kw)
    return CanonicalJob(**base)


def test_remote_kept():
    score, hard_fail, _ = loc.evaluate(_job(remote=True, workplace_type="remote"), PROFILE)
    assert hard_fail is False and score == 1.0


def test_local_onsite_kept():
    _, hard_fail, _ = loc.evaluate(
        _job(workplace_type="onsite", location_name="Tampa, FL"), PROFILE)
    assert hard_fail is False


def test_far_onsite_dropped():
    _, hard_fail, _ = loc.evaluate(
        _job(workplace_type="onsite", location_name="San Francisco, CA"), PROFILE)
    assert hard_fail is True


def test_far_hybrid_dropped():
    _, hard_fail, _ = loc.evaluate(
        _job(workplace_type="hybrid", location_name="Los Angeles, California"), PROFILE)
    assert hard_fail is True


def test_unknown_location_kept():
    _, hard_fail, _ = loc.evaluate(
        _job(workplace_type="onsite", location_name="Someplace Nobody Knows"), PROFILE)
    assert hard_fail is False    # geocode gap -> don't silently drop

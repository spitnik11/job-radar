"""Required-vs-preferred is the crux of the seniority filter (spec section 6)."""

from app.matching.seniority import classify_seniority, is_suppressed, parse_experience


def test_required_years_parsed():
    lo, hi, req = parse_experience("Minimum of 5 years of experience required.")
    assert hi == 5 and req is True


def test_preferred_years_not_required():
    _, hi, req = parse_experience("3-5 years preferred, or equivalent experience.")
    assert hi == 5 and req is False


def test_range_upper_bound():
    lo, hi, req = parse_experience("We want 2 to 4 years of hands-on support experience.")
    assert lo == 2 and hi == 4 and req is True


def test_no_years():
    assert parse_experience("Great entry-level opportunity, no experience needed.") == (None, None, False)


def test_classify():
    assert classify_seniority("Senior Software Engineer") == "senior"
    assert classify_seniority("Staff Backend Engineer") == "staff"
    assert classify_seniority("Engineering Manager") == "manager"
    assert classify_seniority("Junior Application Developer") == "junior"
    assert classify_seniority("Application Support Analyst") == "mid"


def test_suppression_rules():
    # staff/manager titles hide
    assert is_suppressed("staff", None, False)[0] is True
    assert is_suppressed("manager", None, False)[0] is True
    # 6+ required years hides; 5 does not (that's a penalty, not a hide)
    assert is_suppressed("mid", 6, True)[0] is True
    assert is_suppressed("mid", 5, True)[0] is False
    # preferred years never hide, even at 8
    assert is_suppressed("mid", 8, False)[0] is False
    # a plain relevant role stays visible
    assert is_suppressed("mid", None, False)[0] is False

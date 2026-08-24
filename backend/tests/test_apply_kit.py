"""Kit normalization: quoted résumé paths get cleaned, casual EEO answers become the standard
dropdown text an application form actually offers, and unknowns are left untouched."""

from app import apply_kit


def test_resume_path_strips_windows_copy_as_path_quotes():
    kit = apply_kit._normalize(apply_kit.ApplicationKit(resume_path='"C:\\Users\\x\\r.pdf"'))
    assert kit.resume_path == "C:\\Users\\x\\r.pdf"


def test_eeo_casual_inputs_canonicalize_to_form_option_text():
    kit = apply_kit._normalize(apply_kit.ApplicationKit(
        gender="male", race="black", veteran_status="not a veteran", disability_status="not disabled"))
    assert kit.gender == "Male"
    assert kit.race == "Black or African American"
    assert kit.veteran_status == "I am not a protected veteran"
    assert kit.disability_status == "No, I do not have a disability"


def test_decline_and_unknown_values_are_preserved():
    kit = apply_kit._normalize(apply_kit.ApplicationKit(
        gender=apply_kit.DECLINE, race="Some self-described identity"))
    assert kit.gender == apply_kit.DECLINE
    assert kit.race == "Some self-described identity"   # never overwritten / fabricated

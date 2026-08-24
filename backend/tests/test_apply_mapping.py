"""Field mapping: standard fields fill from the kit, EEO values match a dropdown's option text,
verbose gating questions ('will you...require sponsorship...') don't get mis-read as location,
and questions with no rule are surfaced as open (never fabricated)."""

from app.apply.mapping import map_fields
from app.apply_kit import ApplicationKit

KIT = ApplicationKit(
    full_name="Gabriel Pina", email="g@example.com", phone="8135073123",
    city="Brandon", state="FL", country="United States",
    linkedin="https://linkedin.com/in/x", github="https://github.com/x",
    resume_path="C:/r.pdf", authorized_us=True, needs_sponsorship=False,
    gender="Male", race="Black or African American",
    veteran_status="I am not a protected veteran", desired_salary="60000",
)


def _f(label, type="text", options=None, required=False):
    return {"label": label, "type": type, "name": label, "id": "", "options": options or [], "required": required}


def test_standard_fields_and_resume_upload():
    out = map_fields(KIT, [_f("First Name"), _f("Email"), _f("Résumé", "file"), _f("Legal Name")])
    got = {f["label"]: (f.get("option") or f["value"]) for f in out["filled"]}
    assert got["First Name"] == "Gabriel"
    assert got["Email"] == "g@example.com"
    assert got["Legal Name"] == "Gabriel Pina"
    assert got["Résumé (upload)"] == "C:/r.pdf"


def test_sponsorship_question_not_mislabeled_as_location():
    out = map_fields(KIT, [_f("Will you now or in the future require visa sponsorship?")])
    assert out["filled"][0]["value"] == "No"          # -> needs_sponsorship, not "Brandon, FL"


def test_eeo_value_matches_dropdown_option():
    opts = ["Male", "Female", "Decline to self-identify"]
    out = map_fields(KIT, [_f("Gender", "select", options=opts)])
    assert out["filled"][0]["option"] == "Male"


def test_unknown_question_is_open_not_invented():
    out = map_fields(KIT, [_f("Describe a hard problem you solved.", "textarea")])
    assert not out["filled"]
    assert out["open"][0]["label"].startswith("Describe a hard problem")

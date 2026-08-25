"""Map the Application Kit onto a form's fields by label keywords — the deterministic 90% (name,
email, phone, links, résumé, work-auth, EEO, common screeners). Anything it can't map with
confidence is returned as an open question for a later LLM tier to answer (Phase C); Phase A just
surfaces those, it never invents answers."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..apply_kit import ApplicationKit

YES, NO = "Yes", "No"


def _first_last(full: str) -> tuple[str, str]:
    parts = (full or "").split()
    return (parts[0], parts[-1]) if len(parts) >= 2 else (full, "")


def _yn(val) -> str:
    return YES if val else NO


# (matcher on lowercased label) -> function(kit) -> value.  Order matters: first hit wins, so more
# specific labels (last name, cover letter) are listed before generic ones (name, letter).
def _rules(kit: ApplicationKit):
    first, last = _first_last(kit.full_name)
    loc = ", ".join([p for p in (kit.city, kit.state) if p])
    return [
        (lambda l: "cover letter" in l,                     kit.cover_letter_template or "[tailored per job — Phase C]"),
        (lambda l: re.search(r"\b(first|given)\b.*name|^first$", l),   first),
        (lambda l: re.search(r"\b(last|family|sur)\b.*name|^last$", l), last),
        (lambda l: "full name" in l or "legal name" in l or (l.strip() in ("name", "your name", "legal name")), kit.full_name),
        (lambda l: "preferred name" in l,                   first),
        (lambda l: "email" in l,                            kit.email),
        (lambda l: "phone" in l or "mobile" in l,           kit.phone),
        (lambda l: "linkedin" in l,                         kit.linkedin),
        (lambda l: "github" in l,                           kit.github),
        (lambda l: "portfolio" in l or "website" in l or "personal url" in l, kit.portfolio),
        (lambda l: "address" in l and "email" not in l,     kit.address),
        # gating yes/no questions BEFORE the generic location rule — verbose labels often contain
        # "location"/"where" as filler and would otherwise be mis-read as a location field.
        (lambda l: "sponsor" in l or "visa" in l,           _yn(kit.needs_sponsorship)),
        (lambda l: ("authoriz" in l or "legally" in l or "eligible to work" in l or "right to work" in l), _yn(kit.authorized_us)),
        (lambda l: "relocat" in l,                          _yn(kit.willing_relocate)),
        (lambda l: any(w in l for w in ("city", "location", "where are you", "current location")) and "sponsor" not in l, loc or kit.city),
        (lambda l: "state" in l or "province" in l,         kit.state),
        (lambda l: "country" in l,                          kit.country),
        (lambda l: "salary" in l or "compensation" in l or "desired pay" in l, kit.desired_salary),
        (lambda l: "start date" in l or "available" in l or "notice period" in l or ("when" in l and "start" in l) or "start a new role" in l, kit.start_date),
        (lambda l: "years" in l and ("experience" in l or "exp" in l), str(kit.years_experience or "")),
        (lambda l: "gender" in l,                           kit.gender),
        (lambda l: "race" in l or "ethnic" in l,            kit.race),
        (lambda l: "veteran" in l,                          kit.veteran_status),
        (lambda l: "disab" in l,                            kit.disability_status),
        (lambda l: "education" in l or "degree" in l or "highest level" in l, kit.education_level),
        (lambda l: "hear about" in l or "how did you find" in l or "source" in l, kit.hear_about_us),
        (lambda l: "reference" in l,                        _yn(kit.references_available) if kit.references_available is not None else ""),
        (lambda l: "work" in l and "pref" in l,             kit.work_pref),
    ]


def _match_option(value: str, options: list[str]) -> str | None:
    """Pick the dropdown/radio option closest to the kit value (case-insensitive contains, then
    fuzzy). Returns None if nothing is a reasonable match — better to flag than mis-select."""
    if not value or not options:
        return None
    v = value.strip().lower()
    for o in options:                                   # exact / substring first
        ol = o.lower()
        if v == ol or v in ol or ol in v:
            return o
    best, score = None, 0.0
    for o in options:
        r = SequenceMatcher(None, v, o.lower()).ratio()
        if r > score:
            best, score = o, r
    return best if score >= 0.6 else None


def map_fields(kit: ApplicationKit, fields: list[dict]) -> dict:
    """-> {filled:[{label,value,option,type,required}], open:[{label,type,required,options}]}.
    'filled' = what we'd enter; 'open' = custom questions needing an answer (not fabricated)."""
    rules = _rules(kit)
    filled, open_q = [], []
    for f in fields:
        label = (f.get("label") or "").lower()
        req = f.get("required", False)
        jr = f.get("jr")
        ftype, ftag = f.get("type", ""), f.get("tag", "")
        if ftype == "file":         # every file input on an application form is a document upload.
            if "cover" in label:    # we don't hold a cover-letter FILE (only text) -> flag it
                open_q.append({"label": f.get("label"), "type": "file", "jr": jr, "required": req,
                               "options": [], "note": "cover-letter file upload — kit stores text, not a file"})
            else:                   # résumé/CV upload — the field's own label is often wrong, so name it plainly
                filled.append({"label": "Résumé (upload)", "value": kit.resume_path, "option": None,
                               "type": "file", "jr": jr, "required": req})
            continue
        if ftag in ("radio", "buttongroup"):   # single-select via radios OR <button> toggles
            kind = "buttongroup" if ftag == "buttongroup" else "radio"
            val = next((v for pred, v in rules if pred(label)), None)
            opts = f.get("options") or []
            texts = [o["text"] for o in opts]
            chosen = _match_option(str(val), texts) if val not in (None, "") else None
            if chosen is None:
                open_q.append({"label": f.get("label") or f.get("name"), "type": kind, "jr": jr,
                               "required": req, "options": texts,
                               "opt_jrs": {o["text"]: o["jr"] for o in opts}})
            else:
                ojr = next((o["jr"] for o in opts if o["text"] == chosen), None)
                filled.append({"label": f.get("label"), "value": chosen, "option": chosen,
                               "type": kind, "jr": ojr, "required": req})
            continue
        if ftype == "checkbox":     # lone checkbox: only auto-check consent/agreement/acknowledge
            if any(w in label for w in ("agree", "consent", "acknowledg", "confirm", "certify", "terms", "privacy", "read the above")):
                filled.append({"label": f.get("label"), "value": "checked", "option": None,
                               "type": "checkbox", "jr": jr, "required": req, "check": True})
            else:                        # optional demographic/pronoun boxes -> leave for review
                open_q.append({"label": f.get("label") or f.get("name"), "type": "checkbox", "jr": jr,
                               "required": req, "options": []})
            continue
        val = next((v for pred, v in rules if pred(label)), None)
        if val in (None, ""):
            open_q.append({"label": f.get("label") or f.get("name") or "(unlabeled)",
                           "type": ftype, "jr": jr, "required": req, "options": f.get("options") or []})
            continue
        opts = f.get("options") or []
        option = _match_option(str(val), opts) if opts else None
        if opts and option is None:                     # had a dropdown but our value didn't fit -> flag it
            open_q.append({"label": f.get("label"), "type": ftype, "jr": jr, "required": req,
                           "options": opts, "note": f"kit has '{val}' but no matching option"})
            continue
        filled.append({"label": f.get("label") or f.get("name"), "value": str(val),
                       "option": option, "type": ftype, "jr": jr, "required": req})
    return {"filled": filled, "open": open_q}

"""Turn an uploaded resume (PDF/docx/txt/…) into profile fields: skills (reusing the connector
skill detector), years of experience, and education level. markitdown handles the file formats."""

from __future__ import annotations

import os
import re
import tempfile

from .matching.skills import extract_skills

_EDU = [
    ("phd", r"ph\.?\s?d|doctorate"),
    ("master", r"\bmaster'?s?\b|\bm\.?s\.?\b|\bm\.?b\.?a\b|\bmsc\b"),
    ("bachelor", r"\bbachelor'?s?\b|\bb\.?s\.?\b|\bb\.?a\.?s?\b|\ba\.?s\.?\b"),
]
_YEARS = re.compile(r"(\d{1,2})\+?\s*years", re.I)


def extract_text(file_bytes: bytes, filename: str) -> str:
    from markitdown import MarkItDown
    suffix = os.path.splitext(filename)[1] or ".txt"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(file_bytes)
        tmp.close()
        return MarkItDown().convert(tmp.name).text_content
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def parse_resume(file_bytes: bytes, filename: str) -> dict:
    text = extract_text(file_bytes, filename)
    low = text.lower()

    skills = sorted(extract_skills(text))

    education = "unknown"
    for level, pat in _EDU:
        if re.search(pat, low):
            education = level
            break

    yrs = [int(m.group(1)) for m in _YEARS.finditer(low) if int(m.group(1)) <= 40]
    years = max(yrs) if yrs else 0

    return {"skills": skills, "education_level": education,
            "years_experience": years, "text_chars": len(text)}

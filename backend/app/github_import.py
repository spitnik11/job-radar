"""Import portfolio-skill evidence from public GitHub repos (spec sections 57-58).

Maps repo languages + topics + description to canonical skills so the scorer's portfolio factor
reflects real shipped work, not a hand-written list. Public repos only, unauthenticated (60 req/hr
is plenty for an occasional import); a token for private repos is a later add."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .connectors.base import USER_AGENT
from .matching.skills import extract_skills

API = "https://api.github.com"

# GitHub language name -> canonical skill (matches profile.yaml / matching/skills.py)
LANG_TO_SKILL = {
    "Python": "python", "TypeScript": "typescript", "JavaScript": "javascript",
    "HTML": "html_css", "CSS": "html_css", "SCSS": "html_css", "Less": "html_css",
    "Dockerfile": "docker", "PowerShell": "powershell", "Shell": "bash",
    "Jupyter Notebook": "python", "Go": "go", "Rust": "rust", "Java": "java",
    "C#": "csharp", "C++": "cpp", "Ruby": "ruby", "PHP": "php", "Vue": "vue",
    "Kotlin": "kotlin", "Swift": "swift", "Svelte": "vue",
}


def derive_skills(repo: dict, languages: list[str]) -> set[str]:
    """Pure mapping: repo metadata + language list -> canonical skills. Unit-testable, no network."""
    text = f"{repo.get('name', '')} {repo.get('description') or ''} {' '.join(repo.get('topics', []))}"
    skills = extract_skills(text)                       # reuse the connector skill detector
    for lang in languages:
        if lang in LANG_TO_SKILL:
            skills.add(LANG_TO_SKILL[lang])
    return skills


def import_github(username: str) -> dict:
    """Fetch public repos and build {skill: [repo names]} evidence."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    evidence: dict[str, list[str]] = {}
    scanned = 0
    with httpx.Client(timeout=25, headers=headers, follow_redirects=True) as client:
        r = client.get(f"{API}/users/{username}/repos",
                       params={"per_page": 100, "sort": "updated"})
        r.raise_for_status()
        for repo in r.json():
            if repo.get("fork") or repo.get("archived"):
                continue
            scanned += 1
            try:
                lr = client.get(repo["languages_url"])
                languages = list(lr.json().keys()) if lr.status_code == 200 else []
            except httpx.HTTPError:
                languages = []
            for skill in derive_skills(repo, languages):
                evidence.setdefault(skill, []).append(repo["name"])
    return {
        "username": username,
        "repos_scanned": scanned,
        "skills": sorted(evidence.keys()),
        "evidence": evidence,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }

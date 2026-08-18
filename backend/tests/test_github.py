"""GitHub portfolio import — the pure language/topic/description -> skill mapping (no network)."""

from app.github_import import derive_skills


def test_languages_map_to_skills():
    repo = {"name": "purrden", "description": "a game", "topics": []}
    skills = derive_skills(repo, ["Python", "TypeScript", "Dockerfile", "PowerShell", "CSS"])
    assert {"python", "typescript", "docker", "powershell", "html_css"} <= skills


def test_topics_and_description_detected():
    repo = {"name": "svc", "description": "FastAPI + React app, runs on Docker",
            "topics": ["nextjs", "llm"]}
    skills = derive_skills(repo, [])
    assert {"fastapi", "react", "docker", "nextjs", "llm_integration"} <= skills


def test_unknown_language_ignored():
    skills = derive_skills({"name": "x", "description": "", "topics": []}, ["Brainfuck", "Mako"])
    assert skills == set()

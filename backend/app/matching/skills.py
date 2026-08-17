"""Skill detection. Canonical keys match profile.yaml; the vocabulary is deliberately
BROADER than the candidate's skills so a job can mention skills he lacks (that gap is what
the scorer measures). Add aliases here as jobs reveal new phrasings."""

from __future__ import annotations

import re

# canonical -> text aliases (matched case-insensitively with alphanumeric boundaries)
SKILL_PATTERNS: dict[str, list[str]] = {
    # --- candidate skills (weights live in profile.yaml) ---
    "python": ["python"],
    "javascript": ["javascript", "java script"],
    "typescript": ["typescript"],
    "sql": ["sql", "t-sql", "pl/sql"],
    "react": ["react", "react.js", "reactjs"],
    "nextjs": ["next.js", "nextjs"],
    "nodejs": ["node.js", "nodejs", "node"],
    "rest_api": ["rest api", "restful", "rest apis", "web api"],
    "html_css": ["html", "css", "html/css"],
    "llm_integration": ["llm", "large language model", "llms", "genai", "generative ai"],
    "openai": ["openai", "gpt-4", "gpt-3", "chatgpt"],
    "anthropic_claude": ["anthropic", "claude"],
    "grok_api": ["grok"],
    "multi_agent_orchestration": ["multi-agent", "agentic", "agent orchestration"],
    "prompt_engineering": ["prompt engineering"],
    "mcp": ["model context protocol", "mcp server"],
    "comfyui": ["comfyui"],
    "git": ["git"],
    "github": ["github"],
    "github_actions": ["github actions"],
    "docker": ["docker", "containerization", "containers"],
    "cloudflare": ["cloudflare"],
    "ci_cd": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
    "electron": ["electron"],
    "windows": ["windows", "windows 10", "windows 11"],
    "microsoft_365": ["microsoft 365", "office 365", "m365", "o365"],
    "active_directory": ["active directory", "azure ad", "entra id"],
    "sharepoint": ["sharepoint"],
    "outlook": ["outlook", "exchange"],
    "troubleshooting": ["troubleshooting", "troubleshoot", "diagnose"],
    "hardware_support": ["hardware support", "desktop support", "break/fix", "break fix"],
    "networking": ["networking", "tcp/ip", "dns", "dhcp", "vpn"],
    "wireshark": ["wireshark"],
    "documentation": ["documentation", "technical writing", "knowledge base"],
    "customer_facing": ["customer service", "customer-facing", "client-facing", "customer support"],
    "agile": ["agile", "scrum"],
    "jira": ["jira"],
    "notion": ["notion"],
    "trello": ["trello"],
    # --- skills the candidate does NOT have (still detected, so gaps count against a job) ---
    "java": ["java"],
    "csharp": ["c#", ".net", "asp.net", "dotnet"],
    "cpp": ["c++"],
    "go": ["golang", "go developer"],
    "ruby": ["ruby", "rails", "ruby on rails"],
    "php": ["php", "laravel"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"],
    "salesforce": ["salesforce"],
    "servicenow": ["servicenow"],
    "sap": ["sap"],
    "powershell": ["powershell"],
    "bash": ["bash", "shell scripting"],
    "linux": ["linux", "unix", "rhel", "ubuntu"],
    "vmware": ["vmware", "vsphere", "esxi"],
    "powerbi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "angular": ["angular"],
    "vue": ["vue", "vue.js", "vuejs"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "spring": ["spring boot", "spring framework"],
    "kotlin": ["kotlin"],
    "swift": ["swift"],
    "graphql": ["graphql"],
    "mongodb": ["mongodb", "mongo"],
    "postgresql": ["postgresql", "postgres"],
    "mysql": ["mysql"],
    "redis": ["redis"],
    "kafka": ["kafka"],
    "selenium": ["selenium", "cypress", "playwright"],
}

_COMPILED: dict[str, re.Pattern] = {
    skill: re.compile(
        "|".join(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])" for a in aliases)
    )
    for skill, aliases in SKILL_PATTERNS.items()
}


def extract_skills(text: str) -> set[str]:
    """Return the set of canonical skills mentioned anywhere in the text."""
    low = text.lower()
    return {skill for skill, pat in _COMPILED.items() if pat.search(low)}

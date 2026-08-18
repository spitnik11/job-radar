"""Optional semantic re-ranking (spec sections 22, 56). Reorders the feed by description<->profile
similarity (embeddings via Ollama), blended with the deterministic score. AI is an enhancement, not
infrastructure: if Ollama or the model is unavailable, everything degrades to the deterministic order.

Progressive by design: the UI shows the deterministic feed instantly, then calls /rerank to reorder
the visible top. Job embeddings are cached to disk so each job is embedded once."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Optional

import httpx

from .config import DATA_DIR, _load_yaml
from .schemas import CandidateProfile

CACHE_FILE = DATA_DIR / "semantic.cache.json"
_emb_cache: Optional[dict] = None
_profile_emb: dict = {}          # {profile_text: vector} — only the current profile is kept


def _settings() -> dict:
    return _load_yaml("settings.yaml").get("semantic", {})


def enabled() -> bool:
    return bool(_settings().get("enabled", False))


def _cfg() -> tuple[str, str, float]:
    s = _settings()
    return (s.get("endpoint", "http://localhost:11434"),
            s.get("model", "nomic-embed-text"), float(s.get("weight", 0.25)))


def _load_cache() -> dict:
    global _emb_cache
    if _emb_cache is None:
        try:
            _emb_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
        except (json.JSONDecodeError, OSError):
            _emb_cache = {}
    return _emb_cache


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(_emb_cache), encoding="utf-8")
    except OSError:
        pass


def embed(text: str) -> Optional[list[float]]:
    endpoint, model, _ = _cfg()
    try:
        # short timeout: a down/slow Ollama must fail fast, never hang a request or the warm
        r = httpx.post(f"{endpoint}/api/embeddings",
                       json={"model": model, "prompt": text[:2000]}, timeout=8)
        if r.status_code == 200:
            return r.json().get("embedding") or None
    except httpx.HTTPError:
        return None
    return None


def cosine(a: Optional[list], b: Optional[list]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def profile_text(p: CandidateProfile) -> str:
    roles = ", ".join(r.title for r in p.target_roles)
    top = sorted(p.skills, key=lambda s: -p.skills[s])[:20]
    skills = ", ".join(top).replace("_", " ")
    return (f"Target roles: {roles}. Skills: {skills}. "
            f"Experience: {p.years_experience} years, {p.education_level} degree.")


def profile_embedding(p: CandidateProfile) -> Optional[list[float]]:
    txt = profile_text(p)
    if txt in _profile_emb:
        return _profile_emb[txt]
    # persist across sessions so the first rerank isn't a cold 2s embed
    key = "__profile__:" + hashlib.md5(txt.encode("utf-8")).hexdigest()[:12]
    cache = _load_cache()
    v = cache.get(key)
    if v is None:
        v = embed(txt)
        if v is not None:
            cache[key] = v
            _save_cache()
    _profile_emb.clear()
    _profile_emb[txt] = v
    return v


def rerank(items: list[dict], profile: CandidateProfile) -> dict:
    """items: [{id, text, relevance}]. Returns {order: [ids], scores: {id: 0-100}}.
    Returns the input order unchanged if the backend is unavailable."""
    ids = [it["id"] for it in items]
    pemb = profile_embedding(profile)
    if pemb is None:
        return {"order": ids, "scores": {}}
    _, _, w = _cfg()
    cache = _load_cache()
    # cache-ONLY on the request path — never embed inline (embeds are slow). Uncached jobs stay
    # neutral until the background warmer fills them in, so /rerank is always fast.
    raws = [(it["id"], it["relevance"], cosine(pemb, cache[it["id"]]) if it["id"] in cache else None)
            for it in items]

    # cosine values for related jobs cluster in a narrow band; min-max normalize across THIS batch
    # so semantic differences actually move the blended rank (else the deterministic score dominates).
    sims = [s for _, _, s in raws if s is not None]
    lo, hi = (min(sims), max(sims)) if sims else (0.0, 0.0)
    spread = hi - lo

    def norm(s):
        if s is None:
            return 50.0                         # uncached -> neutral, keeps ~deterministic position
        return 100 * (s - lo) / spread if spread > 1e-6 else 50.0

    scored = [(jid, norm(s), (1 - w) * rel + w * norm(s)) for jid, rel, s in raws]
    scored.sort(key=lambda x: -x[2])
    return {"order": [s[0] for s in scored], "scores": {s[0]: round(s[1]) for s in scored}}


def warm_top(repo, limit: int = 200) -> int:
    """Background pre-embedding of the top jobs so /rerank is always a cache hit. Bounded by `limit`."""
    if not enabled():
        return 0
    cache = _load_cache()
    n = 0
    for j in repo.list_jobs(min_score=0, limit=limit):
        if j.id in cache:
            continue
        v = embed(f"{j.title}. {(j.description_text or '')[:500]}")
        if v is not None:
            cache[j.id] = v
            n += 1
            if n % 20 == 0:
                _save_cache()
    _save_cache()
    return n

"""Bulk prepare-to-ready: run up to N queued jobs through the engine (fill + AI-answer + verify +
screenshot), hands-off, in a background thread. Stores a per-job summary so the UI can show which
are submission-ready and which are blocked. Stops at the armed Submit button on every job — the
actual submit is the assisted per-job step (assist.py). Never submits anything itself."""

from __future__ import annotations

import json
import threading

from ..config import DATA_DIR
from . import engine

CACHE = DATA_DIR / "apply_prepared.local.json"      # gitignored (data/*.local.json)
MAX = 50

_state = {"running": False, "done": 0, "total": 0}
_lock = threading.Lock()


def _load() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(results: dict) -> None:
    CACHE.write_text(json.dumps(results, indent=2), encoding="utf-8")


def _summ(j: dict, r: dict) -> dict:
    # keep the flagged questions (label + options) so the UI can let the user answer them once
    questions = [{"label": q.get("label"), "type": q.get("type"),
                  "required": q.get("required", False), "options": q.get("options", [])}
                 for q in r.get("open", []) if q.get("label")]
    return {"job_id": j["id"], "title": j.get("title"), "company": j.get("company_name"),
            "apply_url": j.get("apply_url"), "status": r.get("status"),
            "reason": r.get("reason"), "blockers": r.get("blockers", []),
            "filled": len(r.get("filled", [])), "open": len(r.get("open", [])),
            "questions": questions,
            "submit_text": r.get("submit_text", ""), "shot": r.get("shot", False)}


def status() -> dict:
    with _lock:
        st = dict(_state)
    results = list(_load().values())
    ready = sum(1 for r in results if r.get("status") == "ready_to_submit")
    st.update(results=results, ready=ready)
    return st


def start(jobs: list[dict]) -> bool:
    """Begin a background prepare run over up to MAX jobs. False if one is already running."""
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, done=0, total=min(len(jobs), MAX))
    threading.Thread(target=_run, args=(jobs[:MAX],), daemon=True).start()
    return True


def _run(jobs: list[dict]) -> None:
    results = _load()
    for j in jobs:
        try:
            r = engine.prepare(j)
        except Exception as e:                       # one bad job never stops the batch
            r = {"status": "error", "reason": f"{type(e).__name__}: {e}", "blockers": ["engine error"]}
        results[j["id"]] = _summ(j, r)
        _save(results)
        with _lock:
            _state["done"] += 1
    with _lock:
        _state["running"] = False


def clear() -> None:
    _save({})

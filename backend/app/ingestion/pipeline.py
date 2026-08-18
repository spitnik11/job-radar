"""Ingestion pipeline (spec sections 17-19): fetch -> normalize -> enrich -> scam -> score
-> location filter -> dedupe -> upsert. One source failing never stops the others (spec s.44).

Run standalone:  python -m app.ingestion.pipeline
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import httpx

from ..config import load_profile, load_targets
from ..connectors import CONNECTORS
from ..connectors.base import REQUEST_TIMEOUT, USER_AGENT
from ..db import SessionLocal, init_db
from ..interfaces import SourceTarget
from ..matching import location as loc
from ..matching.scorer import RuleBasedMatchEngine
from ..matching.seniority import classify_seniority, is_suppressed, parse_experience
from ..matching.skills import extract_skills
from ..models import SyncState
from ..repository import SQLiteJobRepository
from ..schemas import CandidateProfile, CanonicalJob
from .scam import is_hard_scam


def _enrich(job: CanonicalJob) -> None:
    text = f"{job.title}\n{job.description_text}"
    job.detected_skills = sorted(extract_skills(text))
    lo, hi, required = parse_experience(text)
    job.required_years_min, job.required_years_max, job.years_required = lo, hi, required
    job.seniority = classify_seniority(job.title)

    scam, reason = is_hard_scam(text)
    supp, supp_reason = is_suppressed(job.seniority, hi, required)
    if scam:
        job.suppressed, job.suppress_reason = True, reason
        job.flags.append("scam-risk")
    elif supp:
        job.suppressed, job.suppress_reason = True, supp_reason


_SYNC_LOCK = threading.Lock()


def run_ingestion(repo: SQLiteJobRepository | None = None,
                  profile: CandidateProfile | None = None) -> dict:
    """Serialized so a manual /sync and the background scheduler never overlap."""
    with _SYNC_LOCK:
        return _ingest(repo, profile)


def _ingest(repo: SQLiteJobRepository | None,
            profile: CandidateProfile | None) -> dict:
    repo = repo or SQLiteJobRepository()
    profile = profile or load_profile()
    engine = RuleBasedMatchEngine()
    targets = load_targets()

    started_at = datetime.now(timezone.utc)     # jobs not re-seen after this get expired
    by_id: dict[str, CanonicalJob] = {}
    per_source: dict[str, dict] = {}
    fetched_boards: set[tuple[str, str]] = set()
    dropped_location = 0

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
                      follow_redirects=True) as client:
        for target in targets:
            connector = CONNECTORS.get(target.connector_id)
            if connector is None:
                continue
            stat = per_source.setdefault(
                target.connector_id, {"fetched": 0, "kept": 0, "errors": 0})
            try:
                raws = connector.fetch(target, client)
            except Exception as exc:  # noqa: BLE001 — one dead board must not stop the sync
                stat["errors"] += 1
                print(f"[warn] {target.connector_id}:{target.token} fetch failed: {exc}")
                continue

            # board fetched OK -> its stored jobs not seen this run have closed (usajobs -> "federal")
            board_token = "federal" if target.connector_id == "usajobs" else target.token
            fetched_boards.add((target.connector_id, board_token))

            for raw in raws:
                try:
                    job = connector.normalize(raw)
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] normalize failed ({target.token}): {exc}")
                    continue
                if not job.title:
                    continue
                stat["fetched"] += 1

                _enrich(job)
                _loc_score, hard_fail, _detail = loc.evaluate(job, profile)
                if hard_fail:
                    dropped_location += 1
                    continue

                result = engine.score(profile, job)
                job.relevance_score = result.relevance
                job.priority_score = result.priority
                job.score_breakdown = result.breakdown
                for f in result.flags:
                    if f not in job.flags:
                        job.flags.append(f)

                by_id[job.id] = job          # exact-id dedupe (spec section 27, level 1)
                stat["kept"] += 1

    stored = repo.upsert_many(list(by_id.values()))
    expired = repo.mark_stale(fetched_boards, started_at)     # close postings that vanished
    _record_sync(per_source)

    summary = {
        "expired": expired,
        "targets": len(targets),
        "fetched": sum(s["fetched"] for s in per_source.values()),
        "kept": len(by_id),
        "stored": stored,
        "dropped_location": dropped_location,
        "per_source": per_source,
    }
    return summary


def _record_sync(per_source: dict[str, dict]) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        for connector_id, stat in per_source.items():
            row = s.get(SyncState, connector_id) or SyncState(connector_id=connector_id)
            row.last_sync = now
            row.jobs_found = stat["kept"]
            row.failure_count = stat["errors"]
            row.status = "error" if stat["errors"] and not stat["fetched"] else "ok"
            s.merge(row)
        s.commit()


if __name__ == "__main__":
    init_db()
    print("Job Radar ingestion...")
    result = run_ingestion()
    print(f"\nTargets: {result['targets']}  Fetched: {result['fetched']}  "
          f"Kept: {result['kept']}  Stored: {result['stored']}  "
          f"Dropped(location): {result['dropped_location']}")
    for src, stat in result["per_source"].items():
        print(f"  {src:12} fetched={stat['fetched']:4} kept={stat['kept']:4} "
              f"errors={stat['errors']}")

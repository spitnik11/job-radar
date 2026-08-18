"""Non-blocking sync trigger + status, shared by the manual /sync endpoint and the scheduler.

The crawl takes ~60-90s; /sync must NOT block on it (spec section 34: show cached jobs instantly,
refresh in the background). start_sync() kicks the work into a daemon thread and returns at once;
the UI polls /sync/status. Only one sync runs at a time (manual and scheduled can't overlap)."""

from __future__ import annotations

import threading

from .ingestion.pipeline import run_ingestion

_lock = threading.Lock()
_running = False
_warming = False
_last_error: str | None = None


def is_running() -> bool:
    return _running


def start_sync(reason: str = "manual") -> bool:
    """Start a background sync. Returns False if one is already in progress."""
    global _running
    with _lock:
        if _running:
            return False
        _running = True
    threading.Thread(target=_run, args=(reason,), daemon=True, name="job-radar-sync").start()
    return True


def _run(reason: str):
    global _running, _last_error
    try:
        r = run_ingestion()
        _last_error = None
        print(f"[sync/{reason}] stored {r['stored']} jobs")
    except Exception as exc:  # noqa: BLE001 — a failed sync must not wedge the flag
        _last_error = str(exc)
        print(f"[sync/{reason}] failed: {exc}")
    finally:
        _running = False                 # crawl done -> the Sync button un-sticks NOW
    _start_warm(reason)                  # embedding warm runs AFTER, on its own flag (can take minutes)


def _start_warm(reason: str) -> None:
    """Warm embeddings in a SEPARATE thread so it never holds the sync 'running' flag
    (warming 200 jobs at ~2s each would otherwise pin the Sync button for minutes)."""
    global _warming
    from . import semantic
    if not semantic.enabled() or _warming:
        return
    _warming = True

    def _worker():
        global _warming
        try:
            from .repository import SQLiteJobRepository
            n = semantic.warm_top(SQLiteJobRepository(), 120)
            print(f"[warm/{reason}] warmed {n} embeddings")
        except Exception as exc:  # noqa: BLE001
            print(f"[warm/{reason}] failed: {exc}")
        finally:
            _warming = False

    threading.Thread(target=_worker, daemon=True, name="job-radar-warm").start()

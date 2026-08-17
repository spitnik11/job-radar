"""Background auto-sync (spec sections 34, 44): refresh on startup (only if stale) then every 4h,
in a daemon thread so the UI shows cached jobs instantly and never blocks on the network."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from .db import SessionLocal
from .models import SyncState
from .sync_manager import start_sync

AUTO_SYNC_SECONDS = 4 * 3600      # every 4 hours while running
STARTUP_STALE_SECONDS = 3600      # only sync on startup if the last sync is > 1h old


def _seconds_since_last_sync():
    with SessionLocal() as s:
        times = [r.last_sync for r in s.execute(select(SyncState)).scalars() if r.last_sync]
    if not times:
        return None
    newest = max(times)
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - newest).total_seconds()


def _loop():
    age = _seconds_since_last_sync()
    if age is None or age > STARTUP_STALE_SECONDS:
        start_sync("startup")                     # non-blocking; skips if one is already running
    while True:
        time.sleep(AUTO_SYNC_SECONDS)
        start_sync("scheduled")


def start_background_sync():
    threading.Thread(target=_loop, daemon=True, name="job-radar-sync").start()

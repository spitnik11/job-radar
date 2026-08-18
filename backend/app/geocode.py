"""Optional precise geocoding via Nominatim (OpenStreetMap), used only as a fallback when the
static city table can't resolve a location. Opt-in (settings.geocoding.enabled) so the core stays
fully offline by default. Results are cached to disk (positive AND negative) and live calls are
rate-limited to 1/sec per Nominatim's usage policy.

# ponytail: geocode ONLY table-misses, and cache forever — the local market is already covered by
# the static table, so in practice this fires for a handful of unusual cities, then never again.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

import httpx

from .config import DATA_DIR, geocoding_enabled
from .connectors.base import USER_AGENT

CACHE_FILE = DATA_DIR / "geocode.cache.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"

_cache: Optional[dict] = None
_lock = threading.Lock()
_last_call = [0.0]


def enabled() -> bool:
    return geocoding_enabled()


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
        except (json.JSONDecodeError, OSError):
            _cache = {}
    return _cache


def _key(place: str) -> str:
    return " ".join(place.lower().split())


def geocode(place: str) -> Optional[tuple[float, float]]:
    """(lat, lon) for a place string, or None. Cache hit = instant, no network."""
    if not place:
        return None
    cache = _load()
    k = _key(place)
    if k in cache:
        v = cache[k]
        return tuple(v) if v else None
    with _lock:
        if k in cache:                         # another thread filled it while we waited
            v = cache[k]
            return tuple(v) if v else None
        wait = 1.0 - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)                   # be a good Nominatim citizen (<=1 req/s)
        coords = None
        try:
            r = httpx.get(NOMINATIM, params={"q": place, "format": "json", "limit": 1,
                                             "countrycodes": "us"},
                          headers={"User-Agent": USER_AGENT}, timeout=15)
            _last_call[0] = time.monotonic()
            if r.status_code == 200 and r.json():
                d = r.json()[0]
                coords = (float(d["lat"]), float(d["lon"]))
        except (httpx.HTTPError, KeyError, ValueError):
            coords = None
        cache[k] = [coords[0], coords[1]] if coords else None
        try:
            CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
        return coords

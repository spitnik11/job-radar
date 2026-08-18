"""Load the candidate profile + search settings + seed companies from data/*.yaml."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from .interfaces import SourceTarget
from .schemas import CandidateProfile

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_yaml(name: str) -> dict:
    with open(DATA_DIR / name, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def load_profile() -> CandidateProfile:
    """The ACTIVE saveable profile (profile.yaml only seeds the first-run 'Default')."""
    from . import profiles
    return profiles.build_candidate(profiles.get_active_data())


import threading as _threading

_reprocessing = False


def reprocess() -> None:
    """Apply a profile/criteria change to the feed: refresh the cached profile, then re-score
    every stored job IN THE BACKGROUND (rescoring 5k+ jobs must not block the request or fight a
    running sync). Location coverage is completed by the next background sync."""
    global _reprocessing
    load_profile.cache_clear()
    if _reprocessing:
        return
    _reprocessing = True

    def _worker():
        global _reprocessing
        try:
            from .repository import SQLiteJobRepository
            SQLiteJobRepository().rescore_all()
        except Exception as exc:  # noqa: BLE001
            print(f"[reprocess] failed: {exc}")
        finally:
            _reprocessing = False

    _threading.Thread(target=_worker, daemon=True, name="job-radar-reprocess").start()


def load_usajobs_creds() -> tuple[Optional[str], Optional[str]]:
    """USAJOBS key + registered email. Local gitignored file first, then env vars. Never committed."""
    secrets = DATA_DIR / "secrets.local.yaml"
    if secrets.exists():
        u = (yaml.safe_load(secrets.read_text(encoding="utf-8")) or {}).get("usajobs") or {}
        if u.get("api_key") and u.get("email"):
            return u["api_key"], u["email"]
    return os.environ.get("USAJOBS_API_KEY"), os.environ.get("USAJOBS_EMAIL")


@lru_cache(maxsize=1)
def geocoding_enabled() -> bool:
    return bool(_load_yaml("settings.yaml").get("geocoding", {}).get("enabled", False))


@lru_cache(maxsize=1)
def load_targets() -> list[SourceTarget]:
    """Flatten companies.yaml into per-connector fetch targets, honoring enabled sources."""
    companies = _load_yaml("companies.yaml")
    enabled = _load_yaml("settings.yaml").get("sources", {})
    targets: list[SourceTarget] = []
    for connector_id, entries in companies.items():
        if not enabled.get(connector_id, True):
            continue
        for e in entries or []:
            targets.append(
                SourceTarget(
                    connector_id=connector_id,
                    token=e["token"],
                    company_name=e.get("name", e["token"]),
                    company_domain=e.get("domain"),
                )
            )
    return targets

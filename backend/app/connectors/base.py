"""Shared connector helpers: HTML->text, date parsing, workplace inference."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Optional

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t\n]*")

USER_AGENT = "JobRadar/0.1 (personal job search; +local)"
REQUEST_TIMEOUT = 20.0


def strip_html(raw: Optional[str]) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<(br|/p|/div|/li|/h[1-6])\s*/?>", "\n", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return _WS_RE.sub("\n", text).strip()


def parse_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):  # epoch millis (Lever) or seconds
        ts = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def infer_workplace(location_text: str, explicit_remote: Optional[bool] = None
                    ) -> tuple[str, bool]:
    low = (location_text or "").lower()
    if explicit_remote is True or "remote" in low or "anywhere" in low:
        return "remote", True
    if "hybrid" in low:
        return "hybrid", False
    return "onsite", False


def norm_employment(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.lower().replace("-", "_").replace(" ", "_")
    return {"fulltime": "full_time", "parttime": "part_time"}.get(v, v)

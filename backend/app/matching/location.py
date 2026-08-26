"""Location / work-mode matching (spec section 7).

# ponytail: radius uses a static Tampa-Bay city -> lat/long table, not a real geocoder.
# It covers the local commute market; precise geocoding (Nominatim) is a V1.1 upgrade.
# The radius itself stays configurable — only the city resolution is approximate.
"""

from __future__ import annotations

import math
from typing import Optional

from ..schemas import CandidateProfile, CanonicalJob

# lowercase city -> (lat, lon). Tampa Bay commute market + a few far cities so onsite-elsewhere
# jobs resolve and get dropped rather than silently passing as "unknown".
CITY_COORDS: dict[str, tuple[float, float]] = {
    "brandon": (27.9378, -82.2859),
    "tampa": (27.9506, -82.4572),
    "riverview": (27.8661, -82.3265),
    "valrico": (27.9389, -82.2367),
    "seffner": (27.9822, -82.2751),
    "plant city": (28.0189, -82.1129),
    "lakeland": (28.0395, -81.9498),
    "temple terrace": (28.0353, -82.3893),
    "lutz": (28.1511, -82.4615),
    "wesley chapel": (28.2397, -82.3279),
    "land o lakes": (28.2189, -82.4590),
    "st petersburg": (27.7676, -82.6403),
    "saint petersburg": (27.7676, -82.6403),
    "st. petersburg": (27.7676, -82.6403),
    "clearwater": (27.9659, -82.8001),
    "largo": (27.9095, -82.7873),
    "pinellas park": (27.8428, -82.6995),
    "palm harbor": (28.0780, -82.7637),
    "dunedin": (28.0197, -82.7718),
    "oldsmar": (28.0339, -82.6651),
    "safety harbor": (27.9903, -82.6926),
    "new port richey": (28.2442, -82.7193),
    "port richey": (28.2717, -82.7196),
    "spring hill": (28.4789, -82.5254),
    "brooksville": (28.5553, -82.3879),
    "sarasota": (27.3364, -82.5307),
    "bradenton": (27.4989, -82.5748),
    "sun city center": (27.7139, -82.3515),
    "apollo beach": (27.7731, -82.4051),
    "ruskin": (27.7209, -82.4340),
    "zephyrhills": (28.2336, -82.1812),
    "dade city": (28.3647, -82.1959),
    # far cities (outside radius) — resolve so onsite-elsewhere gets dropped
    "orlando": (28.5383, -81.3792),
    "miami": (25.7617, -80.1918),
    "jacksonville": (30.3322, -81.6557),
    "fort lauderdale": (26.1224, -80.1373),
    "atlanta": (33.7490, -84.3880),
    "new york": (40.7128, -74.0060),
    "san francisco": (37.7749, -122.4194),
    "seattle": (47.6062, -122.3321),
    "austin": (30.2672, -97.7431),
    "boston": (42.3601, -71.0589),
    "chicago": (41.8781, -87.6298),
    "denver": (39.7392, -104.9903),
    "los angeles": (34.0522, -118.2437),
    "dallas": (32.7767, -96.7970),
}

REMOTE_HINTS = ("remote", "anywhere", "work from home", "wfh", "distributed")

# --- US-only gate -------------------------------------------------------------------------------
# Non-US country/region/city tokens (word-boundary matched). If a job names one of these and NO US
# signal, it's dropped. Ambiguous "Remote" with no geo signal is treated as US-eligible (the seed
# employers are US-HQ'd and default to US), so we don't over-filter valid US remote roles.
import re as _re

_NONUS = {
    "canada", "canadian", "toronto", "vancouver", "montreal", "ottawa", "calgary", "ontario", "quebec",
    "united kingdom", "u.k.", "uk", "england", "london", "manchester", "scotland", "wales", "ireland", "dublin",
    "europe", "european", "emea", "apac", "apj", "latam", "mena", "anz", "nordics", "nordic",
    "germany", "berlin", "munich", "france", "paris", "spain", "madrid", "barcelona", "netherlands",
    "amsterdam", "italy", "rome", "milan", "portugal", "lisbon", "poland", "warsaw", "austria", "vienna",
    "switzerland", "zurich", "sweden", "stockholm", "norway", "oslo", "denmark", "copenhagen", "finland",
    "helsinki", "belgium", "brussels", "czech", "prague", "romania", "bucharest", "greece", "hungary",
    "budapest", "bulgaria", "serbia", "croatia", "estonia", "lithuania", "latvia", "luxembourg",
    "india", "bangalore", "bengaluru", "hyderabad", "mumbai", "delhi", "pune", "chennai", "gurgaon", "noida",
    "singapore", "japan", "tokyo", "china", "beijing", "shanghai", "shenzhen", "hong kong", "korea", "seoul",
    "taiwan", "taipei", "philippines", "manila", "vietnam", "hanoi", "thailand", "bangkok", "malaysia",
    "kuala lumpur", "indonesia", "jakarta", "pakistan", "bangladesh",
    "australia", "sydney", "melbourne", "brisbane", "perth", "new zealand", "auckland",
    "brazil", "brasil", "sao paulo", "rio de janeiro", "mexico", "guadalajara", "argentina",
    "buenos aires", "colombia", "bogota", "chile", "santiago", "peru", "lima", "costa rica",
    "uruguay", "ecuador",
    "israel", "tel aviv", "u.a.e.", "uae", "dubai", "abu dhabi", "saudi", "riyadh", "qatar", "egypt",
    "cairo", "south africa", "johannesburg", "cape town", "nigeria", "lagos", "kenya", "nairobi", "turkey",
    "istanbul", "morocco", "ukraine", "kyiv",
}
_US_STATES = {"al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia",
              "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
              "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt",
              "va", "wa", "wv", "wi", "wy", "dc"}
_US_STATE_NAMES = {"alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
    "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming"}


def is_us(city, region, location_name, title) -> bool:
    """True if the job is (or is plausibly) US-based. Explicit US signal wins even if it also lists a
    non-US region (e.g. 'Remote US; Remote Canada'). Non-US-only → False. No geo signal → US-eligible."""
    loc = " ".join(x for x in (city, region, location_name) if x).lower()
    combined = (loc + " | " + (title or "")).lower()
    us = (bool(_re.search(r"\b(u\.?s\.?a?|united states)\b", loc))
          or bool(_re.search(r",\s*(" + "|".join(_US_STATES) + r")\b", loc))
          or any(_re.search(r"\b" + _re.escape(n) + r"\b", loc) for n in _US_STATE_NAMES)
          or any(c in loc for c in CITY_COORDS))
    if us:
        return True
    if any(_re.search(r"\b" + _re.escape(k) + r"\b", combined) for k in _NONUS):
        return False
    return True                                       # ambiguous ("Remote", empty) → keep as US-eligible


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def _resolve(job: CanonicalJob) -> Optional[tuple[float, float]]:
    candidates = [job.city, job.location_name]
    for text in candidates:
        if not text:
            continue
        low = text.lower()
        # exact "city" or "city, ST"
        first = low.split(",")[0].strip()
        if first in CITY_COORDS:
            return CITY_COORDS[first]
        for city, coords in CITY_COORDS.items():
            if city in low:
                return coords
    # fallback: precise geocoding for any city not in the static table (opt-in, cached)
    from .. import geocode
    if geocode.enabled():
        for text in candidates:
            if text:
                coords = geocode.geocode(text)
                if coords:
                    return coords
    return None


def evaluate(job: CanonicalJob, profile: CandidateProfile) -> tuple[float, bool, str]:
    """Return (score 0-1, hard_fail, detail). hard_fail True => drop before storing."""
    if profile.home_lat is not None and profile.home_lon is not None:
        home = (profile.home_lat, profile.home_lon)          # geo/manual with resolved coords
    else:
        home = CITY_COORDS.get(profile.home_city.lower(), (27.9378, -82.2859))

    # US-only gate — drop anything based outside the United States, remote or not.
    if not is_us(job.city, job.region, job.location_name, job.title):
        return 0.0, True, "outside the US"

    if job.remote:
        if profile.include_remote:
            return 0.85, False, "Remote (US)"          # kept high, but a local job outranks it
        return 0.0, True, "Remote excluded"

    coords = _resolve(job)
    dist = haversine_miles(home, coords) if coords else None

    if job.workplace_type == "hybrid":
        if not profile.include_hybrid:
            return 0.0, True, "Hybrid excluded"
        if dist is None:
            return 0.5, False, "Hybrid, location unknown"
        if dist <= profile.radius_miles:
            return 1.0 - 0.1 * (dist / profile.radius_miles), False, f"Hybrid, {dist:.0f} mi"
        # hybrid = some in-office days, so a far hybrid role is as impractical as far onsite -> drop
        return 0.0, True, f"Hybrid {dist:.0f} mi away (outside {profile.radius_miles} mi)"

    # onsite / unknown workplace type -> treat as onsite
    if not profile.include_onsite and job.workplace_type == "onsite":
        return 0.0, True, "Onsite excluded"
    if dist is None:
        return 0.35, False, "Location unknown"
    if dist <= profile.radius_miles:
        return 1.0 - 0.1 * (dist / profile.radius_miles), False, f"{dist:.0f} mi away"
    return 0.0, True, f"{dist:.0f} mi away (outside {profile.radius_miles} mi)"

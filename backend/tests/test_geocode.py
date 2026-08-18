"""Geocoding fallback — cache behavior and the offline-by-default guard (no live network in tests)."""

from app import geocode


def test_cache_hit_returns_without_network():
    cache = geocode._load()
    cache["testville, zz"] = [10.5, 20.5]          # key = normalized "Testville,  ZZ"
    assert geocode.geocode("Testville,  ZZ") == (10.5, 20.5)


def test_negative_cache_returns_none():
    geocode._load()["nowhere town, zz"] = None
    assert geocode.geocode("Nowhere Town, ZZ") is None


def test_disabled_by_default():
    assert geocode.enabled() is False              # settings.geocoding.enabled defaults false

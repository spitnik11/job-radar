"""Profile store: seed, create/activate/update/delete, and build_candidate (incl. GitHub merge)."""

from app import profiles


def test_seed_creates_active_default():
    plist = profiles.list_profiles()
    assert plist and any(p["active"] for p in plist)
    cp = profiles.build_candidate(profiles.get_active_data())
    assert cp.skills                                     # Default seeded from yaml


def test_build_merges_github_and_location():
    data = {"skills": {"python": 1.0}, "target_roles": [], "github_skills": ["docker"],
            "home": {"city": "Austin", "region": "TX", "lat": 30.27, "lon": -97.74, "mode": "manual"}}
    cp = profiles.build_candidate(data)
    assert "docker" in cp.portfolio_skills and cp.skills["docker"] == 0.6   # gh evidence merged
    assert cp.home_lat == 30.27 and cp.home_city == "Austin"


def test_create_activate_update_delete_cycle():
    pid = profiles.create("Test", {"skills": {"java": 1.0}, "target_roles": [],
                                    "home": {"city": "Reno"}, "radius_miles": 25})
    try:
        assert profiles.activate(pid)
        assert profiles.get_active()[1]["home"]["city"] == "Reno"
        assert profiles.update(pid, {"radius_miles": 99})
        assert profiles.get_active()[1]["radius_miles"] == 99
    finally:
        default = next(p["id"] for p in profiles.list_profiles() if p["id"] != pid)
        profiles.activate(default)
        profiles.delete(pid)
    assert all(p["id"] != pid for p in profiles.list_profiles())

"""Streak milestone progression: 50, 150, then x*2+50."""

from app.streak import milestones, state


def test_milestone_progression():
    assert milestones(2000)[:5] == [50, 150, 350, 750, 1550]


def test_not_lit_before_first():
    s = state(30)
    assert s["tier"] == 0 and s["flame"] == 0 and s["next_milestone"] == 50  # flame 0 -> UI greys flame_1
    assert s["remaining"] == 20 and s["progress"] == 60


def test_first_milestone_lights_fire():
    s = state(50)
    assert s["tier"] == 1 and s["flame"] == 1 and s["next_milestone"] == 150 and s["remaining"] == 100


def test_mid_progress():
    s = state(250)                       # between 150 and 350
    assert s["tier"] == 2 and s["next_milestone"] == 350
    assert s["progress"] == 50 and s["remaining"] == 100


def test_flame_caps_at_five():
    assert state(5000)["flame"] == 5     # ms: 50,150,350,750,1550,3150,6350 -> tier 6, flame capped 5

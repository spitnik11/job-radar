"""Application milestone/streak math. Milestones: 50, 150, then x*2+50 (350, 750, 1550, …)."""

from __future__ import annotations


def milestones(upto: int) -> list[int]:
    ms = [50]
    while ms[-1] <= upto:
        ms.append(ms[-1] * 2 + 50)
    return ms


def state(count: int) -> dict:
    ms = milestones(count)
    reached = [m for m in ms if m <= count]
    tier = len(reached)
    base = reached[-1] if reached else 0
    next_m = next(m for m in ms if m > count)
    span = next_m - base
    return {
        "count": count,
        "tier": tier,                     # 0 = fire not yet lit
        "flame": min(tier, 5),            # which flame_N asset (we ship 5)
        "next_milestone": next_m,
        "remaining": next_m - count,
        "progress": round(100 * (count - base) / span) if span else 0,
    }

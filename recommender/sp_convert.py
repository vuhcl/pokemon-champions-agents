"""EV ↔ SP conversion (ADR-003b / ADR-015): ÷8 / round / cap 32 at L50."""

from __future__ import annotations

_STATS = ("hp", "atk", "def", "spa", "spd", "spe")


def evs_to_sp(evs: dict[str, int]) -> dict[str, int]:
    return {k: min(32, round(int(evs.get(k, 0)) / 8)) for k in _STATS}


if __name__ == "__main__":
    assert evs_to_sp({"hp": 252, "atk": 0, "def": 0, "spa": 0, "spd": 4, "spe": 252}) == {
        "hp": 32,
        "atk": 0,
        "def": 0,
        "spa": 0,
        "spd": 0,
        "spe": 32,
    }
    assert evs_to_sp({"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}) == {
        k: 0 for k in _STATS
    }
    assert all(v <= 32 for v in evs_to_sp({k: 999 for k in _STATS}).values())
    print("sp_convert ok")

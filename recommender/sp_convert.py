"""EV ↔ SP conversion (ADR-003b / ADR-015): ÷8 / round / cap 32 at L50."""

from __future__ import annotations

_STATS = ("hp", "atk", "def", "spa", "spd", "spe")
# Local mirror of recommend.SP_BUDGET — keep this module dependency-light.
_SP_BUDGET = 66


def evs_to_sp(evs: dict[str, int]) -> dict[str, int]:
    """Convert mainline EVs to Champions SP (0–32).

    Faithful integerization first. If the source spent a full EV budget
    (ΣEV >= 508) but rounding left the SP total under 66, complete via
    largest-remainder (fractional loss, then _STATS order). Under-508
    sources are not padded.
    """
    raw = {k: int(evs.get(k, 0)) for k in _STATS}
    base = {k: min(32, round(raw[k] / 8)) for k in _STATS}
    if sum(raw.values()) < 508:
        return base
    need = _SP_BUDGET - sum(base.values())
    for _ in range(need):
        best_k: str | None = None
        best_loss = float("-inf")
        for k in _STATS:
            if raw[k] <= 0 or base[k] >= 32:
                continue
            loss = min(32.0, raw[k] / 8) - base[k]
            if loss > best_loss:
                best_loss = loss
                best_k = k
        if best_k is None:
            break
        base[best_k] += 1
    return base


if __name__ == "__main__":
    assert evs_to_sp({"hp": 0, "atk": 252, "def": 0, "spa": 0, "spd": 4, "spe": 252}) == {
        "hp": 0,
        "atk": 32,
        "def": 0,
        "spa": 0,
        "spd": 2,
        "spe": 32,
    }
    assert sum(evs_to_sp({"hp": 0, "atk": 252, "def": 0, "spa": 0, "spd": 4, "spe": 252}).values()) == 66
    assert evs_to_sp({"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}) == {
        k: 0 for k in _STATS
    }
    assert all(v <= 32 for v in evs_to_sp({k: 999 for k in _STATS}).values())
    print("sp_convert ok")

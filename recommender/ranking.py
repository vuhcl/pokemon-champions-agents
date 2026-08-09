"""Generic rank-and-cut: sort by key, tiered admission, cut toward n."""

from __future__ import annotations

from typing import Callable, Literal, TypeVar

T = TypeVar("T")
K = TypeVar("K")
OwnershipMode = Literal["owned_first", "owned_last", "off", "owned_only"]
_SOFT_OWNERSHIP_MODES = {"owned_first", "owned_last"}
_OWNERSHIP_MODES = _SOFT_OWNERSHIP_MODES | {"off", "owned_only"}


def rank_and_cut(
    candidates: list[T],
    key: Callable[[T], K],
    n: int,
    tier: Callable[[T], int] | None = None,
    slack: int | float = 0,
    order: Literal["ascending", "descending"] = "descending",
    ownership_mode: OwnershipMode = "off",
    is_owned: Callable[[T], bool] | None = None,
) -> list[T]:
    """Sort candidates by ``key``, optionally admit by tier, cut toward ``n``.

    ``n < 0`` raises ``ValueError``. ``n == 0`` is valid: with tiering, tier 0 is
    still kept in full (Rule 1) and no tier-1+ candidates are admitted; without
    tiering, the result is ``[]``.

    When ``tier`` is ``None``, behavior is flat sort-and-slice to ``n`` (``slack``
    unused). ``order`` selects sort direction for ``key``; default is
    ``"descending"`` (higher key preferred) because that matches typical ranking
    keys (usage, commitment, severity), but it remains a real parameter so
    callers can prefer low keys (e.g. anti-meta) without negating ``key``.

    Soft ownership modes add one boolean component to the effective composite
    key. ``owned_first`` places it before all existing criteria; ``owned_last``
    places it after them. For tiered ranking, the tier index is part of those
    existing criteria for final output order, while admission rules are
    unchanged. ``owned_only`` performs no filtering here: callers must restrict
    their existing candidate pool before ranking.

    Tier grouping uses whatever indices ``tier(c)`` returns. Lookups always use
    an empty list ``[]`` for missing indices — never ``None`` into ``sorted``.

    Rule 1 — Tier 0 is always returned in full, unconditionally. It is never
    sliced or skipped. If tier 0 alone exceeds ``n``, the result exceeds ``n``.
    ``n`` is a target/convenience cap for tiers 1+, not an absolute ceiling.

    Rule 2 — Other tiers (ascending index) use a two-phase check:
      (a) If ``len(out) < n``: sort this tier and slice to fill up to ``n``.
      (b) Else (bonus tier): keep the tier whole if it fits the slack bound;
          otherwise skip it entirely (never partial-slice a bonus tier).

    Rule 3 — ``slack`` dispatch (checked in this order):
      - ``type(slack) is int`` and ``slack == -1``: STRICT — never keep a bonus
        tier. Opt-in; not the default.
      - int (any other, default ``0``): ADDITIVE — bonus bound = ``n + slack``.
        ``slack=0`` means bound = ``n`` (no bonus room).
      - float: MULTIPLICATIVE — bonus bound = ``round(slack * n)`` as a **total**
        (Python ``round``, half-even). ``slack=1.0`` means bound = ``n``.

    Int and float are two different formulas (additive-from-zero vs
    multiplicative-from-one) that both express "no bonus room" via their own
    identity value (``0`` vs ``1.0``). This is deliberate — do not unify them.
    Float ``-1.0`` uses the multiplicative formula; it is not the strict
    sentinel.

    Worked examples (bonus phase, ``n`` already reached):

    - Additive ``slack=2``, ``n=5``: bound = 7. A 2-member bonus fits
      (``5+2<=7``); a 3-member bonus is skipped.
    - Multiplicative ``slack=1.5``, ``n=10``: bound = ``round(15)=15``. A
      4-member bonus fits; a 6-member bonus is skipped.
    - Strict ``slack=-1``: any bonus tier is skipped.
    - Identities ``slack=0`` (int) and ``slack=1.0`` (float): both → no bonus
      room once ``n`` is reached.
    """
    if ownership_mode not in _OWNERSHIP_MODES:
        raise ValueError(f"unsupported ownership_mode: {ownership_mode!r}")
    soft_ownership = ownership_mode in _SOFT_OWNERSHIP_MODES
    if soft_ownership and is_owned is None:
        raise ValueError(f"{ownership_mode} requires is_owned")
    if n < 0:
        raise ValueError("n must be >= 0")
    rev = order == "descending"

    def _soft_key(c: T) -> tuple:
        base = key(c)
        parts = base if isinstance(base, tuple) else (base,)
        if tier is not None:
            tier_index = tier(c)
            parts = ((-tier_index if rev else tier_index), *parts)
        owned = is_owned(c) if is_owned is not None else False
        ownership = owned if rev else not owned
        return (
            (ownership, *parts)
            if ownership_mode == "owned_first"
            else (*parts, ownership)
        )

    rank_key = _soft_key if soft_ownership else key
    if tier is None:
        return sorted(candidates, key=rank_key, reverse=rev)[:n]

    buckets: dict[int, list[T]] = {}
    for c in candidates:
        buckets.setdefault(tier(c), []).append(c)

    out: list[T] = []
    # Rule 1 — always, even when absent (empty list, never None)
    out.extend(sorted(buckets.get(0, []), key=rank_key, reverse=rev))

    for t in sorted(k for k in buckets if k != 0):
        ranked = sorted(buckets.get(t, []), key=rank_key, reverse=rev)
        if len(out) < n:  # Rule 2a — fill to n
            out.extend(ranked[: n - len(out)])
            continue
        # Rule 2b + Rule 3 — bonus keep-whole-or-skip
        if type(slack) is int and slack == -1:
            continue
        bound = round(slack * n) if isinstance(slack, float) else n + slack
        if len(out) + len(ranked) <= bound:
            out.extend(ranked)
    return sorted(out, key=rank_key, reverse=rev) if soft_ownership else out

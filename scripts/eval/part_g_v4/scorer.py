#!/usr/bin/env python3
"""Part G gate scorer skeleton (ADR-060: reads answers JSONL + frozen keys only; no recommender imports).

Verdicts follow R6. The headline gate is a one-sided 95% Clopper-Pearson upper bound on the false rate
over scored claims (TRUE + FALSE); UNVERIFIABLE is excluded from that denominator and reported on its own
line. Scoring rules for usage lists and guaranteed-KO answers live here, in code and tests. Per-template
extractors (answer text -> structured claim) are stubs until dev outputs exist.

    python scripts/eval/part_g_v4/scorer.py --answers answers.jsonl --battery claim_battery.json [--audit-size N --audit-seed S]
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

ALPHA = 0.05
GATE_RATE = 0.02
DESIGN_FLOOR = 240  # scored claims the design wants out of the 384 slots


class Verdict(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNVERIFIABLE = "UNVERIFIABLE"


# None stands for "no verdict" (hedge, incomplete list, no typed claim); it is never counted.
Result = Verdict | None


# --- Clopper-Pearson ---------------------------------------------------------------------------

def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 1.0 if k >= n else 0.0
    lp, lq = math.log(p), math.log1p(-p)
    return sum(
        math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
        for i in range(k + 1)
    )


def cp_upper(false: int, scored: int, alpha: float = ALPHA) -> float:
    """One-sided (1-alpha) Clopper-Pearson upper bound on the false rate: the p where P(X <= false) = alpha."""
    if scored <= 0:
        return 1.0
    if false >= scored:
        return 1.0
    lo, hi = false / scored, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _binom_cdf(false, scored, mid) > alpha else (lo, mid)
    return hi


def min_scored_for(false: int, rate: float = GATE_RATE) -> int:
    """Smallest number of scored claims at which `false` false claims still gives an upper bound <= rate."""
    n = max(false, 1)
    while cp_upper(false, n) > rate:
        n += 1
    return n


@dataclass(frozen=True)
class Claim:
    """One typed claim. `line` is "gate" or "ko_chance" (the numeric KO chance, reported on its own line)."""
    kind: str
    subject: str
    proposition: str
    verdict: Result
    line: str = "gate"  # "gate" | "ko_chance" (KO counts and percents) | "usage_pct" | "threshold_arith_unverifiable" | "chance_nhko_unverifiable"
    reason: str = ""  # e.g. "different_source", or "stated 17.75 vs key 17.906" on a usage_pct claim
    ctype: str = ""  # battery claim type of the item (typing, damage, ...), for the per-type false rate
    span: tuple[int, int] | None = None  # character offsets of the evidence in the answer's final_text (audit view only)
    copied_unchanged: bool = False  # set by the extractor: the value string is verbatim in the item's tool results and states no relation


def dedupe(claims: list[Claim]) -> list[Claim]:
    """One claim per distinct (kind, subject, proposition) per item; negation is already resolved by the extractor
    into the proposition (a bool or a value), and a hedge is a claim with verdict None."""
    seen: dict[tuple[str, str, str], Claim] = {}
    for c in claims:
        seen.setdefault((c.kind, norm(c.subject), norm(c.proposition)), c)
    return list(seen.values())


def _counts(claims: list[Claim]) -> tuple[int, int, int, int]:
    c = Counter(x.verdict for x in claims)
    return c[Verdict.TRUE], c[Verdict.FALSE], c[Verdict.UNVERIFIABLE], c[None]


def _line(claims: list[Claim]) -> dict[str, Any]:
    t, f, u, n = _counts(claims)
    return {"true": t, "false": f, "unverifiable": u, "no_verdict": n, "cp_upper_bound": cp_upper(f, t + f)}


def gate_summary(claims: list[Claim], slots: int, floor: int = DESIGN_FLOOR, gate_ko_chance: bool = True,
                 gate_usage_pct: bool = False) -> dict[str, Any]:
    """Headline over line "gate" claims, plus the KO-number line ("ko_chance": KO counts and KO percents) unless
    gate_ko_chance is off, plus the usage-percentage line only when gate_usage_pct is on. Every line is also reported on
    its own; the usage line lists each mismatched value, and the per-type false rate sits beside the headline."""
    included = {"gate"} | ({"ko_chance"} if gate_ko_chance else set()) | ({"usage_pct"} if gate_usage_pct else set())
    gated = [c for c in claims if c.line in included]
    true, false, unver, none = _counts(gated)
    scored = true + false
    ucb = cp_upper(false, scored)
    per_type: dict[str, dict[str, Any]] = {}
    for ct in sorted({c.ctype for c in gated}):
        t, f, *_ = _counts([c for c in gated if c.ctype == ct])
        per_type[ct or "(untyped)"] = {"false": f, "scored": t + f, "false_rate": f / (t + f) if t + f else None}
    by = lambda ln: [c for c in claims if c.line == ln]  # noqa: E731
    kept = [c for c in gated if not c.copied_unchanged]
    kt, kf, *_ = _counts(kept)
    return {
        "false": false, "true": true, "scored": scored, "slots": slots,
        "answer_rate": scored / slots if slots else None,
        "scored_vs_design_floor": {"floor": floor, "meets": scored >= floor},
        "no_verdict": none,
        "cp_upper_bound": ucb, "gate_rate": GATE_RATE, "passes_gate": scored > 0 and ucb <= GATE_RATE,
        "false_rate_by_type": per_type,
        "unverifiable": {"count": unver, "share_of_typed": unver / (scored + unver) if scored + unver else None},
        "ko_chance_line": {"gating": gate_ko_chance, **_line(by("ko_chance"))},
        "usage_pct_line": {"gating": gate_usage_pct, **_line(by("usage_pct")),
                           "mismatches": [(c.ctype, c.subject, c.proposition, c.reason) for c in by("usage_pct") if c.verdict == Verdict.FALSE]},
        # Sensitivity only: the same headline without claims the extractor flagged copied_unchanged. It never decides pass or fail.
        "sensitivity_excluding_copied_unchanged": {"false": kf, "scored": kt + kf, "cp_upper_bound": cp_upper(kf, kt + kf), "decides_pass_fail": False,
                                                   "claims_excluded": len(gated) - len(kept)},
        "chance_nhko_unverifiable_line": {"count": len(by("chance_nhko_unverifiable")),
                                          "claims": [(c.subject, c.proposition, c.reason) for c in by("chance_nhko_unverifiable")]},
        "threshold_arith_unverifiable_line": {"count": len(by("threshold_arith_unverifiable")),
                                              "claims": [(c.subject, c.proposition, c.reason) for c in by("threshold_arith_unverifiable")]},
    }


# --- scoring rules -----------------------------------------------------------------------------

def norm(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def ranks(entries: list[tuple[str, float | None]]) -> dict[str, int]:
    """Rank of each key member: competition ranking on the listed percentage (ties share a rank), or list
    position when the list carries no percentages (in-game teammates)."""
    if any(p is None for _, p in entries):
        return {norm(n): i for i, (n, _) in enumerate(entries, 1)}
    return {norm(n): 1 + sum(1 for _, q in entries if q > p) for n, p in entries}


def score_set(kind: str, subject: str, stated: list[str], key: list[str], *, key_source: str,
              stated_source: str | None = None, asserted_ranks: dict[str, int] | None = None,
              key_ranks: dict[str, int] | None = None) -> list[Claim]:
    """Usage lists. `key` is the key's list for the source the prompt names (held items: ranks 1-N plus entries tied
    with rank N; in-game teammates: not extended). The prompt's source is inherited unless the answer names another,
    which makes every claim UNVERIFIABLE against this key. A stated key member is TRUE and a stated non-key member is
    FALSE wherever it sits in the list; unstated key members get no claim. Order is scored only through an asserted
    rank (its own claim, kind `<kind>_rank`)."""
    inherited = stated_source is None or stated_source == key_source
    keyset = {norm(k) for k in key}
    why = "" if inherited else "different_source"
    claims = [Claim(kind, subject, m, (Verdict.TRUE if norm(m) in keyset else Verdict.FALSE) if inherited else Verdict.UNVERIFIABLE, reason=why)
              for m in stated]
    for m, r in (asserted_ranks or {}).items():
        v = Verdict.UNVERIFIABLE if not inherited else (Verdict.TRUE if (key_ranks or {}).get(norm(m)) == r else Verdict.FALSE)
        claims.append(Claim(f"{kind}_rank", subject, f"{m}={r}", v, reason=why))
    return dedupe(claims)


@dataclass(frozen=True)
class KoAnswer:
    """Structured damage answer; None means the answer did not say."""
    yes_no: bool | None
    chance_pct: float | None
    conditions_match: bool  # the stated conditions equal the prompt's
    stated_form_abilities: dict[str, str] | None = None  # side -> ability the answer gave for a Mega side
    ko_count: int | None = None  # "k of the 16 rolls KO"


def score_guaranteed_ko(ans: KoAnswer, gt: dict[str, Any]) -> list[Claim]:
    """gt is the damage claim's ground_truth. Yes/no is scored against guaranteed_ko. A stated KO count is TRUE iff it equals
    rolls_ko_of_16 exactly; a stated KO percent is TRUE iff within chance_tolerance_points of 100*k/16. Counts and percents sit on
    the "ko_chance" line (gated by default). If a Mega form's stated ability differs from the form's single ability, the ability
    claim is FALSE and the damage claims are UNVERIFIABLE."""
    subj = f"{gt['attacker']} {gt['move']} {gt['defender']}"
    out: list[Claim] = []
    form_key = (gt.get("scoring") or {}).get("form_ability_used_by_key") or {}
    wrong_ability = False
    for side, stated in (ans.stated_form_abilities or {}).items():
        want = form_key.get(side)
        if want and norm(stated) != norm(want):
            wrong_ability = True
            out.append(Claim("has_ability", gt[side], stated, Verdict.FALSE, ctype="damage"))
    k = gt["rolls_ko_of_16"]
    if wrong_ability or not ans.conditions_match:
        v = lambda present: Verdict.UNVERIFIABLE if present else None  # noqa: E731
        yn, ch, cnt = v(ans.yes_no is not None), v(ans.chance_pct is not None), v(ans.ko_count is not None)
    else:
        yn = None if ans.yes_no is None else (Verdict.TRUE if ans.yes_no == gt["guaranteed_ko"] else Verdict.FALSE)
        ch = None if ans.chance_pct is None else (
            Verdict.TRUE if abs(ans.chance_pct - 100 * k / 16) <= gt["scoring"]["chance_tolerance_points"] else Verdict.FALSE)
        cnt = None if ans.ko_count is None else (Verdict.TRUE if ans.ko_count == k else Verdict.FALSE)
    out.append(Claim("guaranteed_ko", subj, {None: "hedge", True: "yes", False: "no"}[ans.yes_no], yn, ctype="damage"))
    out.append(Claim("ko_chance", subj, f"{ans.chance_pct}", ch, line="ko_chance", ctype="damage"))
    if ans.ko_count is not None:
        out.append(Claim("ko_count", subj, f"{ans.ko_count}", cnt, line="ko_chance", ctype="damage"))
    return out


# Quantities a damage key holds: the roll list, the defender's HP and the min and max roll.
KEYED = {"hp": "hp", "max_roll": "max_roll", "min_roll": "min_roll"}


def _key_has_arith_data(gt: dict[str, Any]) -> bool:
    return all(f in gt for f in ("rolls", "hp"))


def score_ko_threshold(gt: dict[str, Any], threshold: float) -> Claim:
    """"Rolls of `threshold` or higher KO": TRUE iff the rolls at or above the threshold are exactly the rolls at or above the
    defender's HP. UNVERIFIABLE (own line) if the key lacks the roll list or the HP."""
    subj, prop = f"{gt.get('attacker')} {gt.get('move')} {gt.get('defender')}", f"KO at {threshold:g} or higher"
    if not _key_has_arith_data(gt):
        return Claim("ko_threshold", subj, prop, Verdict.UNVERIFIABLE, line="threshold_arith_unverifiable", reason="key lacks rolls or hp", ctype="damage")
    same = {r for r in gt["rolls"] if r >= threshold} == {r for r in gt["rolls"] if r >= gt["hp"]}
    return Claim("ko_threshold", subj, prop, Verdict.TRUE if same else Verdict.FALSE, ctype="damage",
                 reason="" if same else f"defender hp {gt['hp']}")


def score_hp_arithmetic(gt: dict[str, Any], lhs: tuple[str, float], op: str, rhs: tuple[str, float]) -> Claim:
    """A comparison between two labelled quantities, e.g. ("max_roll", 183) "<" ("hp", 177). FALSE if a labelled value differs from the
    key or the comparison is arithmetically false; UNVERIFIABLE (own line) if a label is not keyed or the key lacks the data."""
    subj, prop = f"{gt.get('attacker')} {gt.get('move')} {gt.get('defender')}", f"{lhs[0]}={lhs[1]:g} {op} {rhs[0]}={rhs[1]:g}"
    if not _key_has_arith_data(gt) or any(lbl not in KEYED for lbl, _ in (lhs, rhs)) or any(KEYED[lbl] not in gt for lbl, _ in (lhs, rhs)):
        return Claim("hp_arithmetic", subj, prop, Verdict.UNVERIFIABLE, line="threshold_arith_unverifiable", reason="label or key data missing", ctype="damage")
    wrong = [f"{lbl} {val:g} vs key {gt[KEYED[lbl]]}" for lbl, val in (lhs, rhs) if val != gt[KEYED[lbl]]]
    holds = {"<": lhs[1] < rhs[1], ">": lhs[1] > rhs[1], "<=": lhs[1] <= rhs[1], ">=": lhs[1] >= rhs[1]}[op]
    ok = not wrong and holds
    return Claim("hp_arithmetic", subj, prop, Verdict.TRUE if ok else Verdict.FALSE, ctype="damage",
                 reason="; ".join(wrong) or ("" if holds else "comparison is false"))


def _subj(gt: dict[str, Any]) -> str:
    return f"{gt.get('attacker')} {gt.get('move')} {gt.get('defender')}"


def _unverifiable(kind: str, subj: str, prop: str, why: str, line: str = "threshold_arith_unverifiable", ctype: str = "damage") -> Claim:
    return Claim(kind, subj, prop, Verdict.UNVERIFIABLE, line=line, reason=why, ctype=ctype)


def score_labelled(gt: dict[str, Any], label: str, value: float) -> Claim:
    """A labelled value ("the defender has 32 HP", "32 SP out of 608 total HP" = hp 608) is FALSE if it differs from the key.
    A label the key does not hold is UNVERIFIABLE on its own line."""
    subj, prop = _subj(gt), f"{label}={value:g}"
    if label not in KEYED or KEYED[label] not in gt:
        return _unverifiable("labelled_value", subj, prop, f"no key field for label {label!r}")
    want = gt[KEYED[label]]
    return Claim("labelled_value", subj, prop, Verdict.TRUE if value == want else Verdict.FALSE, ctype="damage",
                 reason="" if value == want else f"labelled {label} {value:g} vs key {want}")


def score_ko_needed(gt: dict[str, Any], needed: float) -> Claim:
    """"Damage needed to KO" must equal the defender's HP exactly; 197 for HP 196 and "half of HP" are FALSE."""
    subj, prop = _subj(gt), f"damage needed to KO = {needed:g}"
    if "hp" not in gt:
        return _unverifiable("ko_needed", subj, prop, "key lacks hp")
    ok = needed == gt["hp"]
    return Claim("ko_needed", subj, prop, Verdict.TRUE if ok else Verdict.FALSE, ctype="damage", reason="" if ok else f"defender hp {gt['hp']}")


def _speed_of(gt: dict[str, Any], species: str) -> int | None:
    for sp, stat in (("s1", "spe1_jolly32"), ("s2", "spe2_timid32")):
        if gt.get(sp) is not None and norm(gt[sp]) == norm(species) and stat in gt:
            return gt[stat]
    return None


def score_speed_stat(gt: dict[str, Any], species: str, value: float) -> Claim:
    """A stated Speed stat is exact against the key's stat for that species. A species the key does not hold is UNVERIFIABLE."""
    subj, prop = f"{gt.get('s1')}|{gt.get('s2')}", f"{species} speed={value:g}"
    want = _speed_of(gt, species)
    if want is None:
        return _unverifiable("speed_stat", subj, prop, "species not in the key's pair", ctype="speed")
    return Claim("speed_stat", subj, prop, Verdict.TRUE if value == want else Verdict.FALSE, ctype="speed",
                 reason="" if value == want else f"stated {value:g} vs key {want}")


def score_speed_margin(gt: dict[str, Any], a: str, b: str, margin: float) -> Claim:
    """A stated margin ("faster by 54 points") is the absolute difference of the key's two stats."""
    subj, prop = f"{gt.get('s1')}|{gt.get('s2')}", f"|{a} - {b}| speed margin={margin:g}"
    sa, sb = _speed_of(gt, a), _speed_of(gt, b)
    if sa is None or sb is None or norm(a) == norm(b):
        return _unverifiable("speed_margin", subj, prop, "species not both in the key's pair", ctype="speed")
    want = abs(sa - sb)
    return Claim("speed_margin", subj, prop, Verdict.TRUE if margin == want else Verdict.FALSE, ctype="speed",
                 reason="" if margin == want else f"stated {margin:g} vs key {want}")


def score_damage_range(gt: dict[str, Any], lo: float, hi: float) -> Claim:
    """A stated damage range is exact against the key's min and max roll."""
    subj, prop = _subj(gt), f"damage range {lo:g}-{hi:g}"
    if "min_roll" not in gt or "max_roll" not in gt:
        return _unverifiable("damage_range", subj, prop, "key lacks min_roll or max_roll")
    ok = (lo, hi) == (gt["min_roll"], gt["max_roll"])
    return Claim("damage_range", subj, prop, Verdict.TRUE if ok else Verdict.FALSE, ctype="damage",
                 reason="" if ok else f"key {gt['min_roll']}-{gt['max_roll']}")


PCT_ROUNDING_POINTS = 0.1  # the calc truncates to one decimal (154/177 = 87.01 -> 87; 183/177 = 103.39 -> 103.3)


def score_percent_of_hp(gt: dict[str, Any], lo_pct: float, hi_pct: float, tol: float = PCT_ROUNDING_POINTS) -> Claim:
    """A stated damage-as-percent-of-HP range against 100*min_roll/hp and 100*max_roll/hp, within rounding."""
    subj, prop = _subj(gt), f"percent of HP {lo_pct:g}-{hi_pct:g}"
    if not all(f in gt for f in ("min_roll", "max_roll", "hp")):
        return _unverifiable("percent_of_hp", subj, prop, "key lacks min_roll, max_roll or hp")
    exp = (100 * gt["min_roll"] / gt["hp"], 100 * gt["max_roll"] / gt["hp"])
    ok = abs(lo_pct - exp[0]) <= tol + 1e-9 and abs(hi_pct - exp[1]) <= tol + 1e-9
    return Claim("percent_of_hp", subj, prop, Verdict.TRUE if ok else Verdict.FALSE, ctype="damage",
                 reason="" if ok else f"key {exp[0]:.2f}-{exp[1]:.2f}")


def score_nhko(gt: dict[str, Any], kind: str, n: int) -> Claim:
    """"Guaranteed nHKO": n == ceil(hp / min_roll). "Possible nHKO": n == ceil(hp / max_roll). Both from the key's min and max roll."""
    subj, prop = _subj(gt), f"{kind} {n}HKO"
    if kind not in ("guaranteed", "possible") or not all(f in gt for f in ("min_roll", "max_roll", "hp")):
        return _unverifiable("nhko", subj, prop, "unknown kind or key lacks min_roll, max_roll or hp")
    want = -(-gt["hp"] // (gt["min_roll"] if kind == "guaranteed" else gt["max_roll"]))
    return Claim("nhko", subj, prop, Verdict.TRUE if n == want else Verdict.FALSE, ctype="damage", reason="" if n == want else f"key {want}HKO")


def score_chance_nhko(gt: dict[str, Any], chance_pct: float, n: int) -> Claim:
    """A chance-based nHKO ("99.8% chance to 3HKO") has no key value: UNVERIFIABLE, reported on its own line."""
    return _unverifiable("chance_nhko", _subj(gt), f"{chance_pct:g}% chance to {n}HKO", "chance-based nHKO has no key value", line="chance_nhko_unverifiable")


def score_ko_ratio(gt: dict[str, Any], num: float, den: float) -> Claim:
    """"k out of d rolls would KO" (also when it is read off an HKO chance): scored against rolls_ko_of_16. Out of 16 the count is
    exact; out of any other d it is compared as a percent, within chance_tolerance_points of 100*k/16."""
    subj, prop = _subj(gt), f"{num:g} of {den:g} rolls KO"
    k = gt["rolls_ko_of_16"]
    if den == 16:
        ok = num == k
    else:
        ok = abs(100 * num / den - 100 * k / 16) <= (gt.get("scoring") or {}).get("chance_tolerance_points", 3.125)
    return Claim("ko_count", subj, prop, Verdict.TRUE if ok else Verdict.FALSE, line="ko_chance", ctype="damage",
                 reason="" if ok else f"key {k} of 16")


def _tool_pct_rows(tool_calls: list[dict[str, Any]]) -> dict[str, list[float]]:
    """name -> every percentage the item's own tool results give for that name (conditional_pct, else pct)."""
    rows: dict[str, list[float]] = {}
    for call in tool_calls:
        res = call.get("result") or {}
        for lst in (v for v in res.values() if isinstance(v, list)):
            for row in lst:
                if isinstance(row, dict) and "name" in row:
                    pct = row.get("conditional_pct", row.get("pct"))
                    if isinstance(pct, (int, float)) and not isinstance(pct, bool):
                        rows.setdefault(norm(row["name"]), []).append(float(pct))
    return rows


def score_usage_pct(kind: str, subject: str, stated: dict[str, float], tool_calls: list[dict[str, Any]], tol: float = 0.05) -> list[Claim]:
    """Stated usage percentages against the item's own tool results (answers.jsonl), not the frozen keys or the pinned data.
    A stated percentage next to a name is FALSE if that name has no row in the tool results, or if no row for it is within
    `tol` points (the tool returns 3 decimals); the mismatch is recorded in `reason`. On the "usage_pct" line, gated only by
    --gate-usage-pct. The scorer reads the values the tool returned and never computes a percentage itself."""
    rows = _tool_pct_rows(tool_calls)
    out = []
    for name, val in stated.items():
        have = rows.get(norm(name))
        if not have:
            out.append(Claim(kind, subject, f"{name}={val:g}", Verdict.FALSE, line="usage_pct", reason="no row for this name in the tool results", ctype="usage"))
            continue
        ok = any(abs(val - v) <= tol + 1e-9 for v in have)
        out.append(Claim(kind, subject, f"{name}={val:g}", Verdict.TRUE if ok else Verdict.FALSE, line="usage_pct", ctype="usage",
                         reason="" if ok else f"stated {val:g} vs tool {', '.join(f'{v:g}' for v in have)}"))
    return dedupe(out)


def score_equal(kind: str, subject: str, stated: Any, key: Any) -> Claim:
    """Yes/no and scalar claims (typing, ability, legality, speed winner, move statics); stated=None is a hedge."""
    if stated is None:
        return Claim(kind, subject, "", None)
    ok = norm(stated) == norm(key) if isinstance(key, str) else stated == key
    return Claim(kind, subject, str(stated), Verdict.TRUE if ok else Verdict.FALSE)


# --- extractors (stubs) ------------------------------------------------------------------------

def _stub(kind: str) -> Callable[[dict[str, Any], dict[str, Any]], Any]:
    def extract(item: dict[str, Any], answer: dict[str, Any]) -> Any:
        raise NotImplementedError(f"extractor for {kind} is not written until dev outputs exist")
    return extract


EXTRACTORS: dict[tuple[str, str], Callable[[dict[str, Any], dict[str, Any]], Any]] = {
    (t, k): _stub(f"{t}/{k}")
    for t, k in [("typing", "has_type"), ("ability", "has_ability"), ("ability_form", "has_ability"), ("item", "item_legal"),
                 ("legality", "species_legal"), ("speed", "outspeed"), ("speed", "faster"), ("damage", "guaranteed_ko"),
                 ("usage", "common_items"), ("usage", "teammates"), ("usage_showdown", "teammates"),
                 ("move_static", "category"), ("move_static", "base_power"), ("move_static", "move_type")]
}


# --- audit sampler -----------------------------------------------------------------------------

def audit_sample(ids: list[str], size: int, seed: int) -> list[str]:
    """Fixed-seed sample of item ids for hand audit; the size is the caller's decision."""
    return sorted(random.Random(seed).sample(sorted(ids), min(size, len(ids))))


# --- pilot report ------------------------------------------------------------------------------

def pilot_report(by_item: dict[str, list[Claim]], n_items: int, slots: int, gate_ko_chance: bool = True, gate_usage_pct: bool = False) -> dict[str, Any]:
    """Counts only (no false counts, no gate verdict): scored claims in the gate's unit (the same lines the headline uses), items with a
    scored claim, UNVERIFIABLE share overall and by kind (every line, including the separate unverifiable lines), and how many claims were
    UNVERIFIABLE because the answer named a different source."""
    included = {"gate"} | ({"ko_chance"} if gate_ko_chance else set()) | ({"usage_pct"} if gate_usage_pct else set())
    every = [c for cs in by_item.values() for c in cs]
    gated = [c for c in every if c.line in included]
    scored = [c for c in gated if c.verdict in (Verdict.TRUE, Verdict.FALSE)]
    unver = [c for c in every if c.verdict == Verdict.UNVERIFIABLE]
    by_kind: dict[str, dict[str, Any]] = {}
    for kind in sorted({c.kind for c in every}):
        u = sum(1 for c in unver if c.kind == kind)
        t = u + sum(1 for c in scored if c.kind == kind)
        by_kind[kind] = {"unverifiable": u, "typed": t, "share": u / t if t else None}
    return {
        "scored_claims_gate_unit": len(scored), "slots": slots, "lines_in_the_gate_unit": sorted(included),
        "items_with_scored_claim": sum(1 for cs in by_item.values() if any(c.line in included and c.verdict in (Verdict.TRUE, Verdict.FALSE) for c in cs)),
        "items": n_items,
        "unverifiable_share_overall": len(unver) / (len(unver) + len(scored)) if unver or scored else None,
        "unverifiable_by_kind": by_kind,
        "answer_names_different_source": sum(1 for c in every if c.reason == "different_source"),
    }


# --- gate-unit variants (non-gating, dev runs only) ---------------------------------------------

# Kinds whose claims are the members of a set-valued answer (a list the answer gives): usage lists, ability lists, type lists.
SET_VALUED_KINDS = {"common_items", "teammates", "ability_list_member", "type_list_member"}
_HEADLINE_LINES = {"gate", "ko_chance"}  # the lines in the gate unit by default


def list_as_one(by_item: dict[str, list[Claim]]) -> list[Claim]:
    """The variant gate unit: every set-valued answer is one claim per item and kind. FALSE if any stated member is FALSE; TRUE if at least one
    member is stated and none is FALSE; no verdict if no member is stated. Other claims in the gate unit stay individual. No verdict rule changes."""
    out: list[Claim] = []
    for iid, cs in by_item.items():
        groups: dict[str, list[Claim]] = {}
        for c in cs:
            if c.line not in _HEADLINE_LINES:
                continue
            if c.kind in SET_VALUED_KINDS:
                groups.setdefault(c.kind, []).append(c)
            else:
                out.append(c)
        for kind, members in groups.items():
            stated = [m for m in members if m.verdict in (Verdict.TRUE, Verdict.FALSE)]
            verdict = None if not stated else (Verdict.FALSE if any(m.verdict == Verdict.FALSE for m in stated) else Verdict.TRUE)
            out.append(Claim(f"set:{kind}", iid, f"{len(stated)} members", verdict, ctype=members[0].ctype,
                             reason="" if verdict != Verdict.FALSE else "; ".join(m.proposition for m in stated if m.verdict == Verdict.FALSE)))
    return out


def _headline_line(claims: list[Claim], slots: int) -> dict[str, Any]:
    true, false, _, _ = _counts([c for c in claims if c.line in _HEADLINE_LINES])
    per_type: dict[str, dict[str, Any]] = {}
    for ct in sorted({c.ctype for c in claims}):
        t, f, *_ = _counts([c for c in claims if c.ctype == ct and c.line in _HEADLINE_LINES])
        per_type[ct or "(untyped)"] = {"claims": t + f, "false": f, "false_rate": f / (t + f) if t + f else None}
    n = true + false
    return {"claims": n, "false": false, "cp_upper_bound": cp_upper(false, n), "passes_gate": n > 0 and cp_upper(false, n) <= GATE_RATE,
            "min_claims_for_this_many_false": min_scored_for(false), "false_rate_by_type": per_type, "slots": slots}


def dev_headline(by_item: dict[str, list[Claim]], slots: int) -> dict[str, Any]:
    """Both headline units side by side with the same Clopper-Pearson table: list members as claims (the existing unit) and list-as-one."""
    every = [c for cs in by_item.values() for c in cs]
    return {"list_members_as_claims": _headline_line(every, slots), "list_as_one": _headline_line(list_as_one(by_item), slots),
            "note": "dev-run only, non-gating; no verdict rule differs between the two lines"}


def dev_headline_allowed(battery: Path, half: str | None, run_params: Path | None) -> tuple[bool, str]:
    """--show-dev-headline is for dev runs on half P only: refused for a seed-0 battery, for any other half, and for a run without a run_params
    record whose hash is intact. (The full run_params verify is for gate runs: it needs a clean tree, which a dev run does not have.)"""
    import hashlib
    try:
        doc = json.loads(battery.read_text())
    except (OSError, json.JSONDecodeError):
        return False, f"cannot read the battery {battery}"
    if doc.get("seed") == 0 or "part_g_v4/battery" in str(battery.resolve()):
        return False, "refused: seed 0 is held out"
    if half != "P":
        return False, "refused: the dev headline is for half P only"
    if run_params is None or not run_params.is_file():
        return False, "refused: no run_params.json for this run"
    rec = json.loads(run_params.read_text())
    body = {k: v for k, v in rec.items() if k != "record_sha256"}
    if rec.get("record_sha256") != hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
        return False, "refused: the run_params record was edited after it was written"
    if rec.get("schema") != "run_parameter_record_v1" or rec.get("allow_live") is not False or (rec.get("arm_config") or {}).get("allow_live") is not False:
        return False, "refused: run_params does not describe an offline arm run"
    return True, "ok"


# --- exception-log gate ------------------------------------------------------------------------

def exception_log_verified(path: Path | None, expected_sha256: str | None, repo: Path | None = None) -> tuple[bool, str]:
    """The headline false rate is printed only once the audit exception log is committed and hashed: the file exists, its sha256 equals the
    stated hash, git tracks it, and it has no uncommitted changes."""
    import hashlib
    import subprocess
    if path is None or not expected_sha256:
        return False, "no exception log and hash given"
    if not path.is_file():
        return False, f"{path} does not exist"
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256.lower():
        return False, "exception log sha256 differs from the stated hash"
    cwd = repo or path.resolve().parent
    run = lambda *a: subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True)  # noqa: E731
    if run("ls-files", "--error-unmatch", str(path.resolve())).returncode != 0:
        return False, "exception log is not committed (git does not track it)"
    if run("diff", "--quiet", "HEAD", "--", str(path.resolve())).returncode != 0:
        return False, "exception log has uncommitted changes"
    return True, "ok"


# --- CLI ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--half", choices=("P", "T"), default=None, help="score one half of the dev split (needs --split-file); P is for parser building")
    ap.add_argument("--split-file", type=Path, default=None)
    ap.add_argument("--claims", type=Path, help="JSONL {id, claims:[[kind,subject,proposition,verdict|null,line,reason]]} instead of the extractors")
    ap.add_argument("--exception-log", type=Path, default=None, help="the committed audit exception log")
    ap.add_argument("--exception-log-sha256", default=None, help="its sha256, as recorded when it was committed")
    ap.add_argument("--show-dev-headline", action="store_true", help="dev runs on half P only: print the list-members and list-as-one headlines (non-gating)")
    ap.add_argument("--run-params", type=Path, default=None, help="the run's run_params.json (default: next to --answers)")
    ap.add_argument("--audit-size", type=int, default=None)
    ap.add_argument("--audit-seed", type=int, default=0)
    ap.add_argument("--gate-ko-chance", action=argparse.BooleanOptionalAction, default=True,
                    help="KO counts and KO percents are gated claims (default on); --no-gate-ko-chance reports them on their own line")
    ap.add_argument("--gate-usage-pct", action="store_true", help="gate stated usage percentages (default off; reported on their own line)")
    args = ap.parse_args()
    items = {i["id"]: i for i in json.loads(args.battery.read_text())["items"] if i.get("gated", True)}
    if args.half:
        if not args.split_file:
            raise SystemExit("--half needs --split-file")
        keep = {i for v in json.loads(args.split_file.read_text())[args.half].values() for i in v}
        items = {k: v for k, v in items.items() if k in keep}
    answers = {r["id"]: r for r in map(json.loads, args.answers.read_text().splitlines()) if r["id"] in items}
    slots = sum(i["n_claims"] for i in items.values())
    if args.audit_size:
        print(json.dumps({"audit_ids": audit_sample(sorted(answers), args.audit_size, args.audit_seed)}))
    if args.claims:
        by_item = {r["id"]: [Claim(k, s_, p, Verdict(v) if v else None, ln, *rest) for k, s_, p, v, ln, *rest in r["claims"]]
                   for r in map(json.loads, args.claims.read_text().splitlines()) if r["id"] in items}
    else:
        import extractors
        by_item = {i: extractors.extract_item(items[i], a) for i, a in answers.items()}
    out: dict[str, Any] = {"pilot": pilot_report(by_item, len(items), slots, args.gate_ko_chance, args.gate_usage_pct)}
    if args.show_dev_headline:
        okd, whyd = dev_headline_allowed(args.battery, args.half, args.run_params or args.answers.parent / "run_params.json")
        if not okd:
            raise SystemExit(whyd)
        out["dev_headline"] = dev_headline(by_item, slots)
    ok, why = exception_log_verified(args.exception_log, args.exception_log_sha256)
    if ok:
        out["gate"] = gate_summary([c for cs in by_item.values() for c in cs], slots, gate_ko_chance=args.gate_ko_chance, gate_usage_pct=args.gate_usage_pct)
    else:
        out["headline"] = f"withheld until the audit exception log is committed and hashed ({why})"
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

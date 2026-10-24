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
    line: str = "gate"  # "gate" | "ko_chance" (KO counts and percents) | "usage_pct" | "threshold_arith_unverifiable"
    reason: str = ""  # e.g. "different_source", or "stated 17.75 vs key 17.906" on a usage_pct claim
    ctype: str = ""  # battery claim type of the item (typing, damage, ...), for the per-type false rate


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


def score_usage_pct(kind: str, subject: str, stated: dict[str, float], key_pcts: dict[str, float], tol: float = 0.05) -> list[Claim]:
    """Stated usage percentages against key values, within `tol` points (the tool returns 3 decimals). A name the key does not
    list is FALSE. The mismatching value is recorded in `reason`. On the "usage_pct" line, gated only by --gate-usage-pct."""
    kp = {norm(n): v for n, v in key_pcts.items()}
    out = []
    for name, val in stated.items():
        want = kp.get(norm(name))
        if want is None:
            out.append(Claim(kind, subject, f"{name}={val:g}", Verdict.FALSE, line="usage_pct", reason="name not in the key", ctype="usage"))
        else:
            ok = abs(val - want) <= tol + 1e-9
            out.append(Claim(kind, subject, f"{name}={val:g}", Verdict.TRUE if ok else Verdict.FALSE, line="usage_pct",
                             reason="" if ok else f"stated {val:g} vs key {want:g}", ctype="usage"))
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

def pilot_report(by_item: dict[str, list[Claim]], n_items: int, slots: int) -> dict[str, Any]:
    """Counts only (no gate verdict): scored claims in the gate unit, items with a scored claim, UNVERIFIABLE share
    overall and by kind, and how many claims were UNVERIFIABLE because the answer named a different source."""
    gated = [c for cs in by_item.values() for c in cs if c.line == "gate"]
    scored = [c for c in gated if c.verdict in (Verdict.TRUE, Verdict.FALSE)]
    unver = [c for c in gated if c.verdict == Verdict.UNVERIFIABLE]
    by_kind: dict[str, dict[str, Any]] = {}
    for kind in sorted({c.kind for c in gated}):
        u = sum(1 for c in unver if c.kind == kind)
        t = u + sum(1 for c in scored if c.kind == kind)
        by_kind[kind] = {"unverifiable": u, "typed": t, "share": u / t if t else None}
    return {
        "scored_claims_gate_unit": len(scored), "slots": slots,
        "items_with_scored_claim": sum(1 for cs in by_item.values() if any(c.line == "gate" and c.verdict in (Verdict.TRUE, Verdict.FALSE) for c in cs)),
        "items": n_items,
        "unverifiable_share_overall": len(unver) / (len(unver) + len(scored)) if unver or scored else None,
        "unverifiable_by_kind": by_kind,
        "answer_names_different_source": sum(1 for c in gated if c.reason == "different_source"),
    }


# --- CLI ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--answers", type=Path, help="answers JSONL (for the audit sample ids)")
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--claims", type=Path, help="JSONL {id, claims:[[kind,subject,proposition,verdict|null,line,reason]]} from an extractor")
    ap.add_argument("--audit-size", type=int, default=None)
    ap.add_argument("--audit-seed", type=int, default=0)
    ap.add_argument("--gate-ko-chance", action=argparse.BooleanOptionalAction, default=True,
                    help="KO counts and KO percents are gated claims (default on); --no-gate-ko-chance reports them on their own line")
    ap.add_argument("--gate-usage-pct", action="store_true", help="gate stated usage percentages (default off; reported on their own line)")
    args = ap.parse_args()
    items = {i["id"]: i for i in json.loads(args.battery.read_text())["items"] if i.get("gated", True)}
    slots = sum(i["n_claims"] for i in items.values())
    if args.audit_size and args.answers:
        ids = [json.loads(line)["id"] for line in args.answers.read_text().splitlines()]
        print(json.dumps({"audit_ids": audit_sample(ids, args.audit_size, args.audit_seed)}))
    if not args.claims:
        raise SystemExit("no --claims: the per-template extractors are stubs until dev outputs are reviewed")
    by_item = {r["id"]: [Claim(k, s_, p, Verdict(v) if v else None, ln, *rest) for k, s_, p, v, ln, *rest in r["claims"]]
               for r in map(json.loads, args.claims.read_text().splitlines())}
    print(json.dumps({"pilot": pilot_report(by_item, len(items), slots),
                      "gate": gate_summary([c for cs in by_item.values() for c in cs], slots, gate_ko_chance=args.gate_ko_chance, gate_usage_pct=args.gate_usage_pct)},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

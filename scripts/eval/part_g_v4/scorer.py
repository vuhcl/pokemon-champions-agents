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
    line: str = "gate"


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


def gate_summary(claims: list[Claim], slots: int, floor: int = DESIGN_FLOOR, gate_ko_chance: bool = False) -> dict[str, Any]:
    """Headline over line "gate" claims (plus "ko_chance" ones only when gate_ko_chance); the KO-chance line is always reported."""
    chance = [c for c in claims if c.line == "ko_chance"]
    gated = [c for c in claims if c.line == "gate" or gate_ko_chance]
    true, false, unver, none = _counts(gated)
    scored = true + false
    ucb = cp_upper(false, scored)
    ct, cf, cu, cn = _counts(chance)
    return {
        "false": false, "true": true, "scored": scored, "slots": slots,
        "answer_rate": scored / slots if slots else None,
        "scored_vs_design_floor": {"floor": floor, "meets": scored >= floor},
        "no_verdict": none,
        "cp_upper_bound": ucb, "gate_rate": GATE_RATE, "passes_gate": scored > 0 and ucb <= GATE_RATE,
        "unverifiable": {"count": unver, "share_of_typed": unver / (scored + unver) if scored + unver else None},
        "ko_chance_line": {"gating": gate_ko_chance, "true": ct, "false": cf, "unverifiable": cu, "no_verdict": cn,
                           "cp_upper_bound": cp_upper(cf, ct + cf)},
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
    claims = [Claim(kind, subject, m, (Verdict.TRUE if norm(m) in keyset else Verdict.FALSE) if inherited else Verdict.UNVERIFIABLE)
              for m in stated]
    for m, r in (asserted_ranks or {}).items():
        v = Verdict.UNVERIFIABLE if not inherited else (Verdict.TRUE if (key_ranks or {}).get(norm(m)) == r else Verdict.FALSE)
        claims.append(Claim(f"{kind}_rank", subject, f"{m}={r}", v))
    return dedupe(claims)


@dataclass(frozen=True)
class KoAnswer:
    """Structured damage answer; None means the answer did not say."""
    yes_no: bool | None
    chance_pct: float | None
    conditions_match: bool  # the stated conditions equal the prompt's
    stated_form_abilities: dict[str, str] | None = None  # side -> ability the answer gave for a Mega side


def score_guaranteed_ko(ans: KoAnswer, gt: dict[str, Any]) -> list[Claim]:
    """gt is the damage claim's ground_truth. Yes/no is scored against guaranteed_ko; a chance is TRUE iff within
    chance_tolerance_points of 100*k/16 and sits on its own line. If a Mega form's stated ability differs from the
    form's single ability, the ability claim is FALSE and the damage claims are UNVERIFIABLE."""
    subj = f"{gt['attacker']} {gt['move']} {gt['defender']}"
    out: list[Claim] = []
    form_key = (gt.get("scoring") or {}).get("form_ability_used_by_key") or {}
    wrong_ability = False
    for side, stated in (ans.stated_form_abilities or {}).items():
        want = form_key.get(side)
        if want and norm(stated) != norm(want):
            wrong_ability = True
            out.append(Claim("has_ability", gt[side], stated, Verdict.FALSE))
    if wrong_ability or not ans.conditions_match:
        bad = Verdict.UNVERIFIABLE
        yn, ch = (bad if ans.yes_no is not None else None), (bad if ans.chance_pct is not None else None)
    else:
        yn = None if ans.yes_no is None else (Verdict.TRUE if ans.yes_no == gt["guaranteed_ko"] else Verdict.FALSE)
        ch = None
        if ans.chance_pct is not None:
            ok = abs(ans.chance_pct - 100 * gt["rolls_ko_of_16"] / 16) <= gt["scoring"]["chance_tolerance_points"]
            ch = Verdict.TRUE if ok else Verdict.FALSE
    out.append(Claim("guaranteed_ko", subj, {None: "hedge", True: "yes", False: "no"}[ans.yes_no], yn))
    out.append(Claim("ko_chance", subj, f"{ans.chance_pct}", ch, line="ko_chance"))
    return out


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


# --- CLI ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--audit-size", type=int, default=None)
    ap.add_argument("--audit-seed", type=int, default=0)
    ap.add_argument("--gate-ko-chance", action="store_true", help="count the numeric KO chance in the headline (pending the owner's decision)")
    args = ap.parse_args()
    items = {i["id"]: i for i in json.loads(args.battery.read_text())["items"] if i.get("gated", True)}
    answers = {r["id"]: r for r in map(json.loads, args.answers.read_text().splitlines())}
    if args.audit_size:
        print(json.dumps({"audit_ids": audit_sample(sorted(answers), args.audit_size, args.audit_seed)}))
    claims: list[Claim] = []
    for iid, it in items.items():
        for claim in it["claims"]:
            if iid in answers:
                EXTRACTORS[(it["claim_type"], claim["kind"])](it, answers[iid])  # stubs raise until written
    print(json.dumps(gate_summary(claims, slots=sum(i["n_claims"] for i in items.values()), gate_ko_chance=args.gate_ko_chance), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

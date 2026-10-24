"""Seeded-error canaries for the audit view (ADR-060: no recommender imports).

Canaries exist only in the audit render path: `apply_canaries` returns display copies of the claims and never touches the originals, the scorer,
the verdicts, the counts or the gate. 20 canaries per audit: 7 wrong_verdict (a displayed verdict is flipped), 7 wrong_extraction (one displayed
value is altered, or two names in a displayed list are swapped) and 6 missed_claim (an extracted claim and its highlight are dropped from the
display). Targets are chosen at random among scored claims, at most one per item, with a fixed seed. The canary list (item_id, canary type, target
claim text, the exact change) is written to a separate file and never printed; the build prints only its sha256 and N.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from scorer import Claim, Verdict

COUNTS = (("wrong_verdict", 7), ("wrong_extraction", 7), ("missed_claim", 6))
N_CANARIES = sum(n for _, n in COUNTS)
GATE_LINES = {"gate", "ko_chance"}


def _scored(c: Claim) -> bool:
    return c.line in GATE_LINES and c.verdict in (Verdict.TRUE, Verdict.FALSE) and c.span is not None


def _alter_number(prop: str) -> str | None:
    """Change one digit of the last number in a displayed value (7 -> 6, 9 -> 8), or None when there is no number."""
    ms = list(re.finditer(r"\d", prop))
    if not ms:
        return None
    m = ms[-1]
    d = int(m.group())
    return prop[:m.start()] + str((d + 1) % 10 if d < 9 else 8) + prop[m.end():]


def _swap_partner(claims: list[Claim], idx: int) -> int | None:
    c = claims[idx]
    for j, o in enumerate(claims):
        if j != idx and _scored(o) and o.kind == c.kind and o.proposition != c.proposition and "=" not in c.proposition and "=" not in o.proposition:
            return j
    return None


def _span_text(answer: dict[str, Any], c: Claim) -> str:
    return " ".join(answer["final_text"][c.span[0]:c.span[1]].split())


def choose_canaries(by_item: dict[str, list[Claim]], answers: dict[str, dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """The canary list. Deterministic for a seed; at most one canary per item; raises if the sample cannot support 20."""
    rng = random.Random(seed)
    order = sorted(by_item)
    rng.shuffle(order)
    used: set[str] = set()
    out: list[dict[str, Any]] = []
    for ctype, n in COUNTS:
        for _ in range(n):
            pick = None
            for iid in order:
                if iid in used:
                    continue
                cs = by_item[iid]
                cand = [k for k, c in enumerate(cs) if _scored(c)]
                if ctype == "wrong_extraction":
                    cand = [k for k in cand if _alter_number(cs[k].proposition) is not None or _swap_partner(cs, k) is not None]
                if ctype == "missed_claim":
                    cand = [k for k in cand if sum(1 for o in cs if o.span == cs[k].span) == 1]
                if cand:
                    pick = (iid, rng.choice(sorted(cand)))
                    break
            if pick is None:
                raise SystemExit(f"the sample cannot support {n} {ctype} canaries (one per item)")
            iid, k = pick
            used.add(iid)
            c = by_item[iid][k]
            rec: dict[str, Any] = {"item_id": iid, "canary_type": ctype, "target_claim_text": _span_text(answers[iid], c),
                                   "displayed_claim": f"{c.kind} | {c.proposition}", "claim_index": k}
            if ctype == "wrong_verdict":
                rec["change"] = f"verdict {c.verdict.value} -> {(Verdict.FALSE if c.verdict == Verdict.TRUE else Verdict.TRUE).value}"
            elif ctype == "missed_claim":
                rec["change"] = "claim and its highlight removed from the display"
            else:
                new = _alter_number(c.proposition)
                if new is not None:
                    rec["change"] = f"displayed value {c.proposition!r} -> {new!r}"
                    rec["altered_claim"] = f"{c.kind} | {new}"
                else:
                    j = _swap_partner(by_item[iid], k)
                    rec["change"] = f"displayed names swapped: {c.proposition!r} <-> {by_item[iid][j].proposition!r}"
                    rec["partner_index"] = j
                    rec["partner_claim"] = f"{by_item[iid][j].kind} | {by_item[iid][j].proposition}"
            out.append(rec)
    return out


def apply_canaries(by_item: dict[str, list[Claim]], canaries: list[dict[str, Any]]) -> dict[str, list[Claim]]:
    """Display copies with the canary changes applied. The input claims and lists are not modified."""
    shown = {i: list(cs) for i, cs in by_item.items()}
    for rec in canaries:
        cs, k, t = shown[rec["item_id"]], rec["claim_index"], rec["canary_type"]
        c = cs[k]
        if t == "wrong_verdict":
            flipped = Verdict.FALSE if c.verdict == Verdict.TRUE else Verdict.TRUE
            cs[k] = replace(c, verdict=flipped, reason="" if flipped == Verdict.TRUE else c.reason)
        elif t == "wrong_extraction":
            if "partner_index" in rec:
                j = rec["partner_index"]
                a, b = cs[k], cs[j]
                cs[k], cs[j] = replace(a, proposition=b.proposition), replace(b, proposition=a.proposition)
            else:
                cs[k] = replace(c, proposition=_alter_number(c.proposition))
        else:  # missed_claim
            cs[k] = None  # type: ignore[call-overload]
    return {i: [c for c in cs if c is not None] for i, cs in shown.items()}


def write_canary_list(path: Path, canaries: list[dict[str, Any]], seed: int) -> str:
    """Write the list and return its sha256. The caller prints only the hash and N."""
    text = json.dumps({"seed": seed, "n": len(canaries), "canaries": canaries}, indent=1, sort_keys=True) + "\n"
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()

#!/usr/bin/env python3
"""Derive which damaging moves succeed or deal damage depending on state the fixed damage conditions do not define.

Source: the pinned Showdown move data (data/moves.ts plus the Champions mod override), parsed per move.
Rule (derived, not hand-picked):
  1. exclude a move whose entry has a success gate: onTry, onTryMove, beforeMoveCallback, priorityChargeCallback,
     onDisableMove, or the futuremove flag;
  2. exclude a move whose basePowerCallback / onBasePower reads turn-history or random state
     (hurtThisTurn, attackedBy, totalFainted, newlySwitched, queue, timesAttacked, moveLastTurnResult,
     randomChance, sourceEffect);
  3. keep a move whose callbacks read only state the fixed conditions define (item, status, stat stages, terrain,
     gravity); those are listed with the state they read.
`hand_supplement` is empty unless a move is added by hand, and then each entry carries its reason.
Writes key_artifacts/move_conditionals.v1.json; `--check` re-derives and fails on a difference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
ROOT = PKG.parents[2]
PIN = PKG / "key_artifacts" / "showdown_moves_ts.pin.json"
OUT = PKG / "key_artifacts" / "move_conditionals.v1.json"

GATE_FIELDS = ("onTry", "onTryMove", "beforeMoveCallback", "priorityChargeCallback", "onDisableMove")
CALLBACK_FIELDS = ("basePowerCallback", "onBasePower")
HISTORY_TOKENS = ("hurtThisTurn", "attackedBy", "totalFainted", "newlySwitched", "queue", "timesAttacked",
                  "moveLastTurnResult", "randomChance", "sourceEffect")
DEFINED_TOKENS = (".item", "getItem", ".status", "positiveBoosts", "isTerrain", "gravity", "statsLoweredThisTurn")

# Hand reading of what each derived exclusion depends on (a reading of the callback source, not a data field).
DEPENDS_ON = {
    "aurawheel": "the user being Morpeko in a specific form (Hunger Switch state)",
    "assurance": "whether the target was already damaged this turn",
    "avalanche": "whether the target damaged the user earlier this turn",
    "beakblast": "a charge-up turn with contact punishment",
    "belch": "the user having eaten a berry in this battle",
    "burnup": "the user being Fire-type (fails otherwise)",
    "doubleshock": "the user being Electric-type (fails otherwise)",
    "fakeout": "being the user's first turn on the field",
    "ficklebeam": "a random 30% power boost",
    "firstimpression": "being the user's first turn on the field",
    "focuspunch": "the user not being hit before it moves (acts last in the turn)",
    "futuresight": "a delayed hit two turns later",
    "lastresort": "the user having used every other move it knows",
    "lastrespects": "how many of the user's side have fainted",
    "payback": "whether the target moves before the user this turn",
    "pollenpuff": "whether the target is an ally (heals instead)",
    "poltergeist": "the target holding an item (fails with none)",
    "ragefist": "how many times the user has been hit",
    "round": "whether an ally used Round earlier this turn",
    "snore": "the user being asleep",
    "steelroller": "terrain being present (fails with none)",
    "stompingtantrum": "whether the user's previous move failed",
    "suckerpunch": "the target selecting a damaging move this turn",
    "temperflare": "whether the user's previous move failed",
    "upperhand": "the target selecting a priority move this turn",
}
for _m in ("bounce", "dig", "dive", "electroshot", "fly", "meteorbeam", "phantomforce", "skyattack", "solarbeam", "solarblade"):
    DEPENDS_ON[_m] = "a charge turn first (the charge flag in flags.v1.json already excludes it)"


def to_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def entries(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r"\n\t([a-z0-9]+): \{\n(.*?)\n\t\},", text, re.S)}


def fields(entry: str) -> dict[str, str]:
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"^\t\t(\w+)[:(]", entry, re.M)]
    out = {}
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(entry)
        out[name] = entry[pos:end]
    return out


def build() -> dict:
    pin = json.loads(PIN.read_text())
    base_p, mod_p = ROOT / pin["path"], ROOT / pin["mod_path"]
    if not (base_p.is_file() and mod_p.is_file()):
        raise SystemExit("Showdown moves.ts cache missing (see key_artifacts/SHOWDOWN_CACHE.md)")
    if hashlib.sha256(base_p.read_bytes()).hexdigest() != pin["moves_ts_sha256"] or \
            hashlib.sha256(mod_p.read_bytes()).hexdigest() != pin["mod_moves_ts_sha256"]:
        raise SystemExit("moves.ts sha256 does not match the pin")
    head = subprocess.run(["git", "-C", str(ROOT / ".cache/pokemon-showdown"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != pin["showdown_commit"]:
        raise SystemExit(f"cache HEAD {head} != pinned {pin['showdown_commit']}")
    base, mod = entries(base_p.read_text()), entries(mod_p.read_text())
    legality = json.loads((ROOT / "data/legality/champions.v1.json").read_text())["moves"]
    static = json.loads((ROOT / "data/moves/static.v1.json").read_text())["moves"]
    excluded, kept = {}, {}
    for mid in sorted(static):
        mv = legality[mid]
        if mv["category"] == "Status" or mv["basePower"] <= 0:
            continue
        f = fields(base.get(mid, ""))
        for k, v in fields(mod.get(mid, "")).items():
            f[k] = f.get(k, "") + v
        reasons = [k for k in GATE_FIELDS if k in f]
        if "futuremove" in f.get("flags", ""):
            reasons.append("flags.futuremove")
        history = sorted({t for k in CALLBACK_FIELDS for t in HISTORY_TOKENS if t in f.get(k, "")})
        reasons += [f"reads {t}" for t in history]
        if reasons:
            excluded[mid] = {"name": mv["name"], "because": reasons, "depends_on": DEPENDS_ON.get(mid, "(see because)"),
                             "basis": "derived from the Showdown move entry"}
        else:
            defined = sorted({t.strip(".") for k in CALLBACK_FIELDS for t in DEFINED_TOKENS if t in f.get(k, "")})
            if any(k in f for k in CALLBACK_FIELDS):
                kept[mid] = {"name": mv["name"], "reads_state_defined_by_the_fixed_conditions": defined}
    return {
        "schema": "part_g_v4_move_conditionals",
        "source": {k: pin[k] for k in ("path", "moves_ts_sha256", "mod_path", "mod_moves_ts_sha256", "showdown_commit")},
        "rule": {"gate_fields": list(GATE_FIELDS), "history_tokens": list(HISTORY_TOKENS), "defined_state_tokens": list(DEFINED_TOKENS)},
        "excluded": excluded,
        "kept_with_defined_state": kept,
        "hand_supplement": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(), sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    if args.check:
        if OUT.read_text() != text:
            print("FAIL: move_conditionals.v1.json differs from a fresh derivation")
            return 1
        print("PASS: move_conditionals.v1.json matches a fresh derivation")
        return 0
    OUT.write_text(text)
    d = json.loads(text)
    print(f"wrote {OUT}: {len(d['excluded'])} excluded, {len(d['kept_with_defined_state'])} kept with defined state")
    return 0


if __name__ == "__main__":
    sys.exit(main())

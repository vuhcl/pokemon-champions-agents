#!/usr/bin/env python3
"""Tool-fidelity oracle: no LLM. For each battery item, call the matching real tool from the item's structured
fields, take the tool output as the answer, and score it with the scorer skeleton against the key.

    python scripts/eval/part_g_arm/oracle.py --battery dev_seed1/claim_battery_v4.json --out runs/oracle

Every non-TRUE claim, and every direct tool-vs-key check (tie extension, Showdown ordering, speed numbers,
damage rolls and conditions), is reported; nothing here edits a key or a scorer rule to make it pass.
Fails (not skips) when the calc service is down.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommender.arm_tools import ArmTools  # noqa: E402
from recommender.calc_client import CalcClient  # noqa: E402
from scripts.eval.part_g_arm.config import ArmConfig  # noqa: E402
from scripts.eval.part_g_arm.run_battery import seed0_gate  # noqa: E402

_spec = importlib.util.spec_from_file_location("part_g_scorer", ROOT / "scripts/eval/part_g_v4/scorer.py")
sc = importlib.util.module_from_spec(_spec)
sys.modules["part_g_scorer"] = sc
_spec.loader.exec_module(sc)

TOP_N = 5


def top_with_ties(rows: list[tuple[str, float | None]], n: int = TOP_N) -> list[str]:
    k = min(n, len(rows))
    while 0 < k < len(rows) and rows[k][1] is not None and rows[k][1] == rows[n - 1][1]:
        k += 1
    return [name for name, _ in rows[:k]]


def damage_args(gt: dict) -> dict:
    off = "atk" if gt["move_category"] == "Physical" else "spa"
    z = {s: 0 for s in ("hp", "atk", "def", "spa", "spd", "spe")}
    att = {"species": gt["attacker"], "nature": gt["nature"], "sp": {**z, off: 32}}
    dfn = {"species": gt["defender"], "nature": "Hardy", "sp": {**z, "hp": 32}}
    if not gt["attacker_is_mega"]:
        att["ability"] = gt["attacker_ability"]
    if not gt["defender_is_mega"]:
        dfn["ability"] = gt["defender_ability"]
    return {"attacker": att, "defender": dfn, "move": gt["move"]}


def run_item(tools: ArmTools, it: dict) -> tuple[list[dict], list, list[dict]]:
    """-> (tool calls, claims, direct tool-vs-key mismatches)"""
    t, claim = it["claim_type"], it["claims"][0]
    gt, kind = claim["ground_truth"], claim["kind"]
    calls: list[dict] = []
    diffs: list[dict] = []

    def call(name: str, **args) -> dict:
        res = tools.call(name, args)
        calls.append({"name": name, "args": args, "result": res})
        return res

    def diff(check: str, tool, key) -> None:
        if tool != key:
            diffs.append({"check": check, "tool": tool, "key": key})

    if t == "typing":
        r = call("get_typing", species=gt["species"])
        diff("types", r.get("types"), gt["types"])
        return calls, [sc.score_equal("has_type", gt["species"], gt["asked_type"] in (r.get("types") or []), gt["has_type"])], diffs
    if t in ("ability", "ability_form"):
        name = gt.get("form_id") or gt["species"]
        r = call("get_abilities", species=name)
        diff("abilities", r.get("abilities"), gt.get("form_abilities") or gt["abilities"])
        return calls, [sc.score_equal("has_ability", name, gt["asked_ability"] in (r.get("abilities") or []), gt["has_ability"])], diffs
    if t == "item":
        r = call("check_item_legal", item=gt["item"])
        return calls, [sc.score_equal("item_legal", gt["item"], r.get("legal_as_held_item"), gt["legal"])], diffs
    if t == "legality":
        r = call("check_species_legal", species=gt["species"])
        return calls, [sc.score_equal("species_legal", gt["species"], r.get("legal"), gt["legal"])], diffs
    if t == "speed":
        a = call("get_speed", species=gt["s1"], nature="Jolly", speed_sp=32)
        b = call("get_speed", species=gt["s2"], nature="Timid", speed_sp=32)
        diff("spe1", a.get("speed"), gt["spe1_jolly32"])
        diff("spe2", b.get("speed"), gt["spe2_timid32"])
        stated = None if a.get("speed") is None or b.get("speed") is None else a["speed"] > b["speed"]
        return calls, [sc.score_equal(kind, f"{gt['s1']}|{gt['s2']}", stated, gt["s1_outspeeds"])], diffs
    if t == "move_static":
        r = call("get_move_static", move=gt["move"])
        field = {"category": "category", "base_power": "base_power", "move_type": "type"}[kind]
        key = gt[{"category": "category", "base_power": "basePower", "move_type": "type"}[kind]]
        return calls, [sc.score_equal(kind, gt["move"], r.get(field), key)], diffs
    if t == "damage":
        args = damage_args(gt)
        r = call("calc_damage", **args)
        diff("damage_rolls", r.get("damage_rolls"), gt["rolls"])
        diff("defender_hp", r.get("defender_hp"), gt["hp"])
        diff("calc_desc", r.get("calc_desc"), gt["calc_desc"])
        if r.get("status") != "ok":
            return calls, [sc.Claim("guaranteed_ko", gt["move"], "tool error", None)], diffs
        hits = sum(1 for x in r["damage_rolls"] if x >= r["defender_hp"])
        ans = sc.KoAnswer(hits == 16, 100 * hits / 16, True)
        return calls, sc.score_guaranteed_ko(ans, gt), diffs
    if t == "usage":
        r = call("get_usage_items", species=gt["species"], source="ingame", n=TOP_N)
        items = [(x["name"], x["pct"]) for x in r.get("items", [])]
        t2 = call("get_usage_teammates", species=gt["species"], source="ingame")
        mates = [x["name"] for x in (t2.get("rows") or [])][:TOP_N]  # in-game teammates: not extended
        diff("common_items listed (top-N + ties)", [n for n, _ in items], gt["common_items"])
        diff("teammates top-N", mates, gt["teammates"])
        cs = sc.score_set("common_items", gt["species"], [n for n, _ in items], gt["common_items"], key_source="in-game")
        cs += sc.score_set("teammates", gt["species"], mates, gt["teammates"], key_source="in-game")
        cs += _missing("common_items", gt["species"], [n for n, _ in items], gt["common_items"])
        cs += _missing("teammates", gt["species"], mates, gt["teammates"])
        return calls, cs, diffs
    if t == "usage_showdown":
        r = call("get_usage_teammates", species=gt["id"], source="showdown")
        rows = r.get("rows") or []
        by_rank = [(x["name"], x["conditional_pct"]) for x in rows]
        by_key_order = sorted(by_rank, key=lambda p: (-p[1], next(x["rank"] for x in rows if x["name"] == p[0])))
        stated = top_with_ties(by_rank)
        diff("top-5 order: tool rank order vs key (-pct, rank) order", [n for n, _ in by_rank[:TOP_N]], [n for n, _ in by_key_order[:TOP_N]])
        diff("teammates top-N + ties", stated, gt["teammates"])
        cs = sc.score_set("teammates", gt["species"], stated, gt["teammates"], key_source="showdown")
        return calls, cs + _missing("teammates", gt["species"], stated, gt["teammates"]), diffs
    raise SystemExit(f"no oracle path for {t}/{kind}")


def _missing(kind: str, subject: str, stated: list[str], key: list[str]) -> list:
    """Unstated key members are no-verdict in scoring; an answer copied from the tool should have none, so report them."""
    have = {sc.norm(s) for s in stated}
    return [sc.Claim(f"{kind}_missing_key_member", subject, k, None) for k in key if sc.norm(k) not in have]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    seed0_gate(args.battery, None, None)
    cfg = ArmConfig()
    try:
        CalcClient(cfg.calc_base_url).health()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"calc service is down at {cfg.calc_base_url} ({exc}); the oracle needs it") from None
    tools = ArmTools(regulation=cfg.regulation, allow_live=cfg.allow_live, calc=CalcClient(cfg.calc_base_url))
    items = json.loads(args.battery.read_text())["items"]
    args.out.mkdir(parents=True, exist_ok=True)
    all_claims, flagged = [], []
    with (args.out / "oracle.jsonl").open("w") as fh:
        for it in items:
            calls, claims, diffs = run_item(tools, it)
            fh.write(json.dumps({"id": it["id"], "claim_type": it["claim_type"], "prompt": it["prompt"], "tool_calls": calls,
                                 "claims": [[c.kind, c.subject, c.proposition, c.verdict, c.line] for c in claims],
                                 "tool_vs_key_diffs": diffs}, sort_keys=True, default=str) + "\n")
            all_claims += claims
            if diffs or any(c.verdict != sc.Verdict.TRUE for c in claims):
                flagged.append({"id": it["id"], "claim_type": it["claim_type"], "key": it["claims"][0]["ground_truth"],
                                "tool_calls": calls, "non_true_claims": [[c.kind, c.subject, c.proposition, c.verdict, c.line] for c in claims
                                                                        if c.verdict != sc.Verdict.TRUE], "diffs": diffs})
    slots = sum(i["n_claims"] for i in items)
    (args.out / "flagged.json").write_text(json.dumps(flagged, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps(sc.gate_summary([c for c in all_claims if "missing_key" not in c.kind], slots=slots), indent=1, default=str))
    print(f"{len(items)} items, {len(flagged)} flagged -> {args.out / 'flagged.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

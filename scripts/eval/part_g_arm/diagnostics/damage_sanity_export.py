# THROWAWAY EXPORT, NOT SCORER CODE. Eight dev3b damage items (seed 20261029) with the conditions, the pinned base stats and the calc's own outputs, for an
# independent sanity read. It holds no battery keys beyond the calc's outputs and compares nothing. Needs the calc service on 127.0.0.1:4173.
# Run (cwd repo root): uv run python scripts/eval/part_g_arm/diagnostics/damage_sanity_export.py
import json, random, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from recommender.arm_tools import ArmTools  # noqa: E402
from recommender.ids import to_id  # noqa: E402
from scripts.eval.part_g_arm.oracle import damage_args  # noqa: E402

SEED = 20261029
K = {i["id"]: i for i in json.load(open(ROOT / "scripts/eval/part_g_arm/dev_seed1/claim_battery_v4.json"))["items"]}
snap = json.load(open(ROOT / "data/legality/champions.v1.json"))
static = json.load(open(ROOT / "data/moves/static.v1.json"))["moves"]
rules = json.load(open(ROOT / "scripts/eval/part_g_v4/key_artifacts/calc_move_rules.v1.json"))  # calc-scan output: final move types and effectiveness exceptions
ids = sorted(random.Random(SEED).sample(sorted(i for i in K if K[i]["claim_type"] == "damage"), 8))
tools = ArmTools(regulation="champions", allow_live=False, include_damage_rolls=True)
ZERO = {s: 0 for s in ("hp", "atk", "def", "spa", "spd", "spe")}


def mon(spec, species_name):
    e = snap["species"][to_id(species_name)]
    return {"species": e["name"], "types": e["types"], "base_stats": e["base_stats"], "nature": spec.get("nature"), "level": 50, "sp": {**ZERO, **(spec.get("sp") or {})},
            "item": None, "pinned_abilities": list(e["abilities"].values())}


rows = []
for i in ids:
    gt = K[i]["claims"][0]["ground_truth"]
    args = damage_args(gt)
    res = tools.calc_damage(args["attacker"], args["defender"], args["move"])
    assert res["status"] == "ok", (i, res)
    mid = to_id(args["move"])
    lm = snap["moves"][mid]
    a, d = mon(args["attacker"], args["attacker"]["species"]), mon(args["defender"], args["defender"]["species"])
    raw_stats = res["request"]  # placeholder replaced below
    rows.append({"id": i, "prompt": K[i]["prompt"], "args": args, "res": res, "mid": mid, "lm": lm, "a": a, "d": d})
probe = [{"move": r["args"]["move"], "def_types": r["d"]["types"]} for r in rows]
node = subprocess.run(["node", "--input-type=module", "-e", """
import {Generations,Move,toID} from '@smogon/calc';
import fs from 'fs';
const G=Generations.get(0); const req=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(req.map(r=>{const m=new Move(G,r.move);
  return {bp:m.bp,type:m.type,category:m.category,target:m.target,overrideOffensiveStat:m.overrideOffensiveStat??null,overrideOffensivePokemon:m.overrideOffensivePokemon??null,
          overrideDefensiveStat:m.overrideDefensiveStat??null,overrideDefensivePokemon:m.overrideDefensivePokemon??null,
          };})));
"""], input=json.dumps(probe), capture_output=True, text=True, cwd=ROOT, check=True)
libmoves = json.loads(node.stdout)
CHART = subprocess.run(["node", "--input-type=module", "-e", """
import {Generations} from '@smogon/calc';
const G=Generations.get(0); const out={};
for (const t of G.types) if (t.name !== '???') out[t.name]=Object.fromEntries(Object.entries(t.effectiveness).filter(([k])=>k!=='???'));
console.log(JSON.stringify(out));
"""], capture_output=True, text=True, cwd=ROOT, check=True)
chart = json.loads(CHART.stdout)  # attacking type -> {defending type: multiplier}, from the calc library
with open(ROOT / "scripts/eval/part_g_arm/damage_sanity_export.jsonl", "w") as fh:
    for r, lib in zip(rows, libmoves):
        res, a, d, mname = r["res"], r["a"], r["d"], r["args"]["move"]
        mid = r["mid"]
        # the final move type: the calc scan's recorded type change for this attacker, ability and move, else the move's own type
        ab = (res.get("ability_resolution") or {}).get("attacker", {}).get("applied") or r["args"]["attacker"].get("ability")
        scan_key = f"{to_id(a['species'])}|{ab}|{mid}"
        final_type = rules["type_changes"].get(scan_key, lib["type"])
        exc = rules["move_effectiveness_exceptions"].get(mname, {})
        per_type = {t: exc.get(t, chart[final_type][t]) for t in d["types"]}
        eff = 1.0
        for v in per_type.values():
            eff *= v
        stats_a, stats_d = res["request"], None
        # all six final stats come from the same calc request; call again for the raw stats block
        raw = tools.calc.calculate({**{k: v for k, v in r["args"]["attacker"].items() if k != "sp"}, "evs": r["args"]["attacker"]["sp"], "level": 50},
                                   {**{k: v for k, v in r["args"]["defender"].items() if k != "sp"}, "evs": r["args"]["defender"]["sp"], "level": 50}, mname, {"gameType": "Doubles"})["raw"]["stats"]
        off_stat = lib["overrideOffensiveStat"] or ("atk" if lib["category"] == "Physical" else "spa")
        def_stat = lib["overrideDefensiveStat"] or ("def" if lib["category"] == "Physical" else "spd")
        off_side = "defender" if lib["overrideOffensivePokemon"] == "target" else "attacker"
        def_side = "attacker" if lib["overrideDefensivePokemon"] == "source" else "defender"
        rolls = res["damage_rolls"]
        tgt = static[mid]["target"]
        fh.write(json.dumps({
            "id": r["id"], "prompt": r["prompt"], "seed": SEED, "source": "runs/dev3b damage item; calc service request and outputs below",
            "attacker": {**a, "ability_used_by_calc": ab}, "defender": {**d, "ability_used_by_calc": (res.get("ability_resolution") or {}).get("defender", {}).get("applied") or r["args"]["defender"].get("ability")},
            "move": {"name": mname, "pinned_type": r["lm"]["type"], "pinned_category": r["lm"]["category"], "pinned_base_power": r["lm"]["basePower"], "pinned_target": tgt,
                     "spread": tgt not in ("normal", "any", "self"), "calc_library": lib},
            "field": {"gameType": "Doubles", "weather": None, "terrain": None, "screens": False, "gravity": False, "room": None, "crit": False, "status": "none", "stat_stages": "none",
                      "hp": "full", "hits": "the move is assumed to hit"},
            "calc_request": res["request"],
            "calc_output": {"attacker_final_stats": raw["attacker"], "defender_final_stats": raw["defender"],
                            "attacker_stat_used": {"stat": off_stat, "side": off_side, "value": raw[off_side][off_stat]},
                            "defender_stat_used": {"stat": def_stat, "side": def_side, "value": raw[def_side][def_stat]},
                            "defender_hp": res["defender_hp"], "damage_rolls": rolls, "min_roll": min(rolls), "max_roll": max(rolls), "calc_desc": res["calc_desc"], "ko_text": res["ko_text"],
                            "ability_resolution": res["ability_resolution"],
                            "final_move_type": final_type, "final_move_type_source": "calc scan (calc_move_rules type_changes)" if scan_key in rules["type_changes"] else "the move's own type in the calc library",
                            "type_effectiveness": {"per_defender_type": per_type, "product": eff, "source": "calc library type chart" + (" plus the calc scan's move exceptions" if exc else "")},
                            "stab": final_type in a["types"], "stab_source": "attacker types (pinned data) contain the final move type"},
        }, sort_keys=True) + "\n")
print("wrote", len(rows), "items", ids)

# THROWAWAY DIAGNOSTIC, NOT SCORER CODE. Lists every gated FALSE verdict of a run (lines gate and ko_chance, halves P and T) with the claim span, the key value it
# was scored against and the scorer rule that fired, for review of verdict correctness. Run (cwd scripts/eval/part_g_arm/): python diagnostics/false_verdicts.py runs/dev3b
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "part_g_v4"))
import extractors as ex
from scorer import Verdict
K = {i["id"]: i for i in json.load(open(HERE.parent / "dev_seed1/claim_battery_v4.json"))["items"]}
split = json.load(open(HERE.parent / "dev_split.json")); half = {i: h for h in "PT" for v in split[h].values() for i in v}
A = {r["id"]: r for r in map(json.loads, open(Path(sys.argv[1]) / "answers.jsonl"))}
RULE = {"labelled_value": ("hp", "score_labelled: a labelled value that differs from the key is FALSE"),
        "ko_needed": ("hp", "score_ko_needed: damage needed to KO must equal the defender HP"),
        "ko_count": ("rolls_ko_of_16", "score_ko_ratio: a KO count out of 16 is exact; out of any other d it is compared as a percent within 3.125 points of 100*k/16"),
        "ko_threshold": ("hp,rolls", "score_ko_threshold: rolls at or above X must be exactly the rolls at or above the HP"),
        "damage_range": ("min_roll,max_roll", "score_damage_range: exact"), "percent_of_hp": ("min_roll,max_roll,hp", "score_percent_of_hp: within 0.1 points"),
        "nhko": ("min_roll,max_roll,hp", "score_nhko: guaranteed = ceil(hp/min), possible = ceil(hp/max)"), "guaranteed_ko": ("guaranteed_ko", "yes/no against guaranteed_ko"),
        "has_type": ("has_type", "score_equal"), "has_ability": ("has_ability", "score_equal"), "item_legal": ("legal", "score_equal"), "species_legal": ("legal", "score_equal"),
        "speed_stat": ("spe1_jolly32,spe2_timid32", "score_speed_stat: exact"), "speed_margin": ("spe1_jolly32,spe2_timid32", "score_speed_margin: |difference|"),
        "outspeed": ("s1_outspeeds", "score_equal"), "faster": ("s1_outspeeds", "score_equal"), "category": ("category", "score_equal"), "move_type": ("type", "score_equal"),
        "base_power": ("basePower", "score_equal")}
n = 0
for i in sorted(K):
    for c in ex.extract_item(K[i], A[i]):
        if c.line in ("gate", "ko_chance") and c.verdict == Verdict.FALSE:
            n += 1
            gt = K[i]["claims"][0]["ground_truth"]
            fields, rule = RULE.get(c.kind, ("", "(no rule recorded for this kind)"))
            key = {f: (gt[f] if f != "rolls" else gt["rolls"]) for f in fields.split(",") if f in gt}
            span = " ".join(A[i]["final_text"][c.span[0]:c.span[1]].split()) if c.span else ""
            print(f"{i} [{half[i]}] | kind {c.kind} | claim {c.proposition!r} | span {c.span} {span!r}\n    key {json.dumps(key)} | reason {c.reason!r}\n    rule: {rule}")
print(n, "gated FALSE verdicts")

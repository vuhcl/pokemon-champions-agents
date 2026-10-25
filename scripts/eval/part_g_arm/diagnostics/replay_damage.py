# THROWAWAY REPLAY DRIVER, NOT SCORER CODE. The 8 dev2 damage items whose answers stated a chance, under V1 (rev-3 prompt) and
# V2 (rev-3 prompt, damage_rolls left out of calc_damage results). A replay is not a revision.
# Run with cwd scripts/eval/part_g_arm/runs/ ; writes replay3/V1/answers.jsonl and replay3/V2/answers.jsonl
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.loop import ArmLoop
K = {i['id']: i for i in json.load(open(Path(__file__).resolve().parent.parent / 'dev_seed1/claim_battery_v4.json'))['items']}
IDS = "damage_000 damage_002 damage_011 damage_016 damage_023 damage_029 damage_040 damage_045".split()
for name, cfg in {"V1": ArmConfig(), "V2": ArmConfig(damage_rolls_in_result=False)}.items():
    arm = ArmLoop(cfg); arm.tools.calc.health()
    out = Path('replay3') / name; out.mkdir(parents=True, exist_ok=True)
    with open(out / 'answers.jsonl', 'w') as fh:
        for i in IDS:
            r = {"id": i, "claim_type": "damage", "variant": name, "prompt_hash": cfg.prompt_hash(), **arm.run_item(K[i]['prompt'])}
            fh.write(json.dumps(r, sort_keys=True) + "\n"); fh.flush()
    print(name, "done", cfg.prompt_hash(), flush=True)

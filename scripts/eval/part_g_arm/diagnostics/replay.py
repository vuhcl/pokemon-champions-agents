# THROWAWAY HEURISTIC, NOT SCORER CODE. Used once to compare dev1 with the replay variants; its yes/no, list and number
# parsing is approximate and every flagged case was read by hand. Not the extractor and not a gate rule.
# Run with the working directory scripts/eval/part_g_arm/runs/ (it reads dev1/answers.jsonl and writes replay/).
# Replay driver: the 40 dev1 no-tool prompts + 10 dev1 tool-backed correct items under variants A, B, C.
import dataclasses, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.loop import ArmLoop
from replay_eval import K, evaluate
A1={r['id']:r for r in map(json.loads,open('dev1/answers.jsonl'))}
no_tool=[i for i,a in A1.items() if not a['tool_calls']]
pick={}
for i,a in sorted(A1.items()):
    if a['tool_calls'] and evaluate(i,a)[0]=='correct': pick.setdefault(K[i]['claim_type'],i)
ids=no_tool+[pick[t] for t in ('typing','ability','ability_form','item','legality','speed','damage','usage','usage_showdown','move_static')]
json.dump({"no_tool":no_tool,"tool_backed_correct":ids[len(no_tool):]},open('replay_ids.json','w'))
V={"A":ArmConfig(no_lookup_tool=False,enforce_first_turn_tool=False),"B":ArmConfig(),"C":ArmConfig(prompt_file="system_prompt_rev1.md")}
for name,cfg in V.items():
    arm=ArmLoop(cfg); arm.tools.calc.health()
    with open(f'replay/{name}.jsonl','w') as fh:
        for i in ids:
            r={"id":i,"claim_type":K[i]['claim_type'],"variant":name,"prompt_hash":cfg.prompt_hash(),**arm.run_item(K[i]['prompt'])}
            fh.write(json.dumps(r,sort_keys=True)+"\n"); fh.flush()
    print(name,"done",flush=True)

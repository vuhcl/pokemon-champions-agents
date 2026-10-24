# THROWAWAY HEURISTIC, NOT SCORER CODE. Dev-run report: counts, abstentions, wrong-tool cases, false-claim candidates
# (asked proposition and extras against the keys and the pinned blob), numeric fidelity and damage-call conditions.
# Heuristic parsing, every flagged case was read by hand. Run: python analyze_dev.py devN   (reads runs/devN/answers.jsonl)
import json, re, sys, collections, statistics as st
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import os; os.chdir(HERE.parent/'runs')
from replay_eval import evaluate,K,SP,names,NM,TYPES,ABIL,sents,mentioned,sid,MV
RUN=sys.argv[1]
A=[json.loads(l) for l in open(f'{RUN}/answers.jsonl')]; D={r['id']:r for r in A}
P=lambda *a: print(*a)
P("items",len(A),"unique",len(D),"stop",dict(collections.Counter(r['stop_reason'] for r in A)))
P("turns",sorted(collections.Counter(r['turns'] for r in A).items()),"max_turns hits",sum(r['stop_reason']=='max_turns' for r in A))
tc=[c for r in A for c in r['tool_calls']]
P("tool calls",len(tc),"not ok",sum(not c['ok'] for c in tc),dict(collections.Counter(c['result'].get('error_kind') for c in tc if not c['ok'])),"invalid tool calls",sum(len(r['invalid_tool_calls']) for r in A))
P("tool names",dict(collections.Counter(c['name'] for c in tc)))
w=collections.defaultdict(list)
for r in A: w[r['claim_type']].append(r['wall_s'])
P("wall total s",round(sum(r['wall_s'] for r in A)))
for k,v in sorted(w.items()): P(f"  {k:15s} n={len(v):3d} total={sum(v):6.0f}s mean={st.mean(v):5.1f} max={max(v):5.1f}")
L=sorted(len(r['final_text']) for r in A); q=lambda p:L[int(p*(len(L)-1))]
P("final_text chars min/p25/med/p75/p95/max",L[0],q(.25),q(.5),q(.75),q(.95),L[-1],"| empty",sum(not r['final_text'].strip() for r in A))
real=lambda r:[c for c in r['tool_calls'] if c['name']!='no_lookup_needed']
P("\nITEMS WITH NO REAL LOOKUP by type:",dict(collections.Counter(r['claim_type'] for r in A if not real(r))))
P("  of which stub-only",sum(1 for r in A if not real(r) and r.get('abstentions',[])),"| neither tool nor stub",sum(1 for r in A if not real(r) and not r.get('abstentions',[])))
P("\nno_lookup_needed by category:",dict(collections.Counter(a['category'] for r in A for a in r.get('abstentions',[]))))
for r in A:
    for a in r.get('abstentions',[]): P("  ",r['id'],a)
P("\nENFORCEMENT firings:",sum(r.get('enforcement',{'reasked':False,'rejected_first_turn_text':''})['reasked'] for r in A))
for r in A:
    if r.get('enforcement',{'reasked':False,'rejected_first_turn_text':''})['reasked']: P("  ",r['id'],"rejected:",r.get('enforcement',{'reasked':False,'rejected_first_turn_text':''})['rejected_first_turn_text'][:100].replace("\n"," "),"| then tools",[c['name'] for c in r['tool_calls']])
P("\nMODEL ERRORS / stop != final:")
for r in A:
    if r['errors'] or r['stop_reason']!='final': P("  ",r['id'],r['stop_reason'],r['errors'])
EXP={'typing':{'get_typing'},'ability':{'get_abilities'},'ability_form':{'get_abilities'},'item':{'check_item_legal'},'legality':{'check_species_legal'},'move_static':{'get_move_static'},'speed':{'get_speed'},'damage':{'calc_damage'},'usage':{'get_usage_items','get_usage_teammates'},'usage_showdown':{'get_usage_teammates'}}
P("\nTOOL-WRONG-FOR-QUESTION (real tools called lack the expected one, or the expected set is not covered):")
for r in A:
    called={c['name'] for c in real(r)}; e=EXP[r['claim_type']]
    if called and not e<=called and not (r['claim_type']=='usage' and False): P("  ",r['id'],"called",sorted(called),"expected",sorted(e),"|",r['final_text'][:80].replace("\n"," "))
P("  (items that called the expected tools plus others:",sum(1 for r in A if real(r) and EXP[r['claim_type']]<={c['name'] for c in real(r)} and {c['name'] for c in real(r)}-EXP[r['claim_type']]),")")
# false-claim candidates
def generic_extras(t,prompt,skip_types=False):
    bad=[]
    for s in sents(t):
        sp=mentioned(s)
        if not sp: continue
        ts=set(x for n in sp for x in names[n]['types']); as_=set(v for n in sp for v in names[n]['abilities'].values())
        rest=s; aa=[]
        for x in ABIL:
            if re.search(r'(?<![\w-])'+re.escape(x)+r'(?![\w-])',rest): aa.append(x); rest=rest.replace(x,' ')
        for n in sp: rest=rest.replace(n,' ')
        if not skip_types:
            for y in TYPES:
                if re.search(r'\b'+y+r'\b',rest) and y not in ts and not re.search(r'\b'+y+r'\b',prompt): bad.append(f"type {y}: {s[:100]}")
        for x in aa:
            if x not in as_ and x not in prompt: bad.append(f"ability {x}: {s[:100]}")
    return bad
P("\nFALSE-CLAIM CANDIDATES (heuristic; asked proposition and extras)")
cand=[]
for r in A:
    it=K[r['id']]; st_,why=evaluate(r['id'],r)
    ex=generic_extras(r['final_text'],it['prompt'],skip_types=it['claim_type'] in('usage','usage_showdown')) if it['claim_type'] not in ('typing','ability','ability_form','legality','item') else []
    if st_!='correct' or ex: cand.append((r['id'],'tool-backed' if real(r) else 'tool-free',st_,why[:4],ex[:2]))
for c in cand: P("  ",c)
P("  counts:",dict(collections.Counter((c[1],c[2]) for c in cand)))
# numeric fidelity
P("\nNUMERIC FIDELITY (non-gating)")
for r in A:
    it=K[r['id']]; t=r['final_text']; ty=it['claim_type']; gt=it['claims'][0]['ground_truth']
    if ty in('usage','usage_showdown'):
        for c in r['tool_calls']:
            for row in c['result'].get('rows') or c['result'].get('items') or []:
                pct=row.get('conditional_pct',row.get('pct'))
                if pct is None: continue
                mm=re.search(re.escape(row['name'])+r'(?![\w-])\**\s*(?:-\s*|[(:]\s*)+(\d+(?:\.\d+)?)%',t)
                if mm:
                    d=len(mm.group(1).split('.')[1]) if '.' in mm.group(1) else 0
                    if abs(float(mm.group(1))-pct)>0.5*10**-d+1e-9: P("  usage pct",r['id'],row['name'],"answer",mm.group(1),"tool",pct)
    if ty=='speed':
        tool={c['args'].get('species'):c['result'].get('speed') for c in r['tool_calls'] if c['name']=='get_speed'}
        stated=set(re.findall(r'\b\d{2,3}\b',t))-set(re.findall(r'\d+',it['prompt']))
        vals=[v for v in tool.values() if isinstance(v,int)]
        ok={str(v) for v in vals}|({str(abs(vals[0]-vals[1]))} if len(vals)==2 else set())  # a stated margin is derived, not a tool value
        extra=stated-ok
        if extra: P("  speed number not in tool output",r['id'],sorted(extra),"tool",tool)
    if ty=='damage':
        calls=[c for c in r['tool_calls'] if c['name']=='calc_damage' and c['ok']]
        if not calls: P("  damage no successful calc",r['id']); continue
        res=calls[-1]['result']; k=res['rolls_that_ko']
        for n in re.findall(r'(\d+)\s*(?:out of|of)\s*(?:the\s*)?(?:possible\s*)?16',t):
            if int(n)!=k: P("  damage roll count",r['id'],"answer",n,"calc",k)
        for p in re.findall(r'(\d+(?:\.\d+)?)\s*%\s*(?:chance(?! to)|of the (?:damage )?rolls)',t):
            if abs(float(p)-100*k/16)>3.125: P("  damage KO chance",r['id'],"answer",p,"calc",100*k/16)
        nums=set(re.findall(r'\b\d+\b',t))
        for key,val in (('damage_range',res['damage_range']),('defender_hp',[res['defender_hp']])):
            pass
        m=re.search(r'(\d+)\s*(?:-|to|and)\s*(\d+)\s*damage',t)
        if m and [int(m.group(1)),int(m.group(2))]!=res['damage_range']: P("  damage range stated",r['id'],m.groups(),"calc",res['damage_range'])
        h=re.search(r'(\d+)\s*HP',t)
        if h and int(h.group(1))!=res['defender_hp'] and 'SP' not in h.group(0): P("  defender HP stated",r['id'],h.group(1),"calc",res['defender_hp'])
# damage conditions
P("\nDAMAGE CALLS")
fields=collections.Counter(); first_ok=0; nd=0; diffs=[]
for r in A:
    if K[r['id']]['claim_type']!='damage': continue
    gt=K[r['id']]['claims'][0]['ground_truth']; off='atk' if gt['move_category']=='Physical' else 'spa'
    cs=[c for c in r['tool_calls'] if c['name']=='calc_damage']
    if cs:
        nd+=1; f=(cs[0]['result'].get('request') or {}).get('field')
        if f is None: P("  first call had no echoed request",r['id'],cs[0]['result'].get('error_kind'),cs[0]['result'].get('message','')[:80])
        else: fields[json.dumps(f,sort_keys=True)]+=1
    for n,c in enumerate(cs,1):
        ar=c['args']; d=[]
        for side,spec,nat,ab,ismega,sp in (('attacker',ar.get('attacker',{}),gt['nature'],gt['attacker_ability'],gt['attacker_is_mega'],{off:32}),('defender',ar.get('defender',{}),'Hardy',gt['defender_ability'],gt['defender_is_mega'],{'hp':32})):
            nm=gt[side]
            if spec.get('species')!=nm: d.append(f"{side}.species={spec.get('species')!r} (prompt {nm!r})")
            if spec.get('nature')!=nat: d.append(f"{side}.nature={spec.get('nature')!r} (prompt {nat})")
            exp={k:0 for k in('hp','atk','def','spa','spd','spe')}; exp.update(sp); got={k:0 for k in exp}; got.update(spec.get('sp') or {})
            if got!=exp: d.append(f"{side}.sp={ {k:v for k,v in got.items() if v} } (prompt {sp})")
            if spec.get('ability') not in (None,'',ab): d.append(f"{side}.ability={spec.get('ability')!r} (prompt {ab!r})")
            if spec.get('ability') in (None,'') and not ismega: d.append(f"{side}.ability omitted (prompt {ab!r})")
            if spec.get('item') not in (None,''): d.append(f"{side}.item={spec['item']!r}")
            if spec.get('boosts') and any(spec['boosts'].values()): d.append(f"{side}.boosts={spec['boosts']}")
        if ar.get('move')!=gt['move']: d.append(f"move={ar.get('move')!r} (prompt {gt['move']!r})")
        f=ar.get('field') or {}
        if set(f)-{'gameType'} or f.get('gameType') not in (None,'Doubles'): d.append(f"field={f}")
        if d: diffs.append((r['id'],n,'ok' if c['ok'] else 'ERR',d))
P("  items with a calc call",nd,"| first call echoed field values:",dict(fields))
P("  calls differing from the prompt:",len(diffs),"of",sum(1 for r in A for c in r['tool_calls'] if c['name']=='calc_damage'))
for d in diffs: P("  ",d)
sys.stdout.flush()

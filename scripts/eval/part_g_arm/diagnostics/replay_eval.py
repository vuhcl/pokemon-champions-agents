# THROWAWAY HEURISTIC, NOT SCORER CODE. Used once to compare dev1 with the replay variants; its yes/no, list and number
# parsing is approximate and every flagged case was read by hand. Not the extractor and not a gate rule.
# Run with the working directory scripts/eval/part_g_arm/runs/ (it reads dev1/answers.jsonl and writes replay/).
# throwaway evaluation helpers for the dev1/replay comparison (heuristic; flagged cases are read by hand). Not the extractor.
import json, re
from pathlib import Path
BASE=str(Path(__file__).resolve().parents[4])+'/'
L=json.load(open(BASE+'data/legality/champions.v1.json')); SP=L['species']; MV=L['moves']
K={i['id']:i for i in json.load(open(BASE+'scripts/eval/part_g_arm/dev_seed1/claim_battery_v4.json'))['items']}
TYPES="Normal Fire Water Electric Grass Ice Fighting Poison Ground Flying Psychic Bug Rock Ghost Dragon Dark Steel Fairy".split()
ABIL=sorted({v for s in SP.values() for v in s['abilities'].values()},key=lambda x:-len(x))
names={s['name']:s for s in SP.values()}; NM=sorted(names,key=lambda x:-len(x))
sid=lambda n: re.sub(r'[^a-z0-9]','',n.lower())
def sents(t): return [x for x in re.split(r'(?<=[.!?])\s+|\n+',t) if x.strip()]
def first(t): return sents(t)[0] if sents(t) else ''
def yn(t):
    f=first(t).lower()
    if re.match(r'^(yes|correct|true)\b',f): return True
    if re.match(r'^(no|not|incorrect|false)\b',f) or re.search(r"does not|doesn't|isn't|is not|not legal",f): return False
    if re.search(r'\b(is|are) legal\b',f): return True
    return None
def mentioned(s):
    out=[];rest=s
    for n in NM:
        if re.search(r'(?<![\w-])'+re.escape(n)+r'(?![\w-])',rest): out.append(n); rest=rest.replace(n,' ')
    return out
def extras(it,t):
    gt=it['claims'][0]['ground_truth']; ty=it['claim_type']; bad=[]
    subj=gt.get('form_id') or sid(gt.get('species',''))
    if subj not in SP: return bad
    skip={gt.get('asked_type'),gt.get('asked_ability')}
    for s in sents(t):
        sp=mentioned(s); ts=set(SP[subj]['types']); as_=set(SP[subj]['abilities'].values())
        for n in sp: ts|=set(names[n]['types']); as_|=set(names[n]['abilities'].values())
        rest=s; aa=[]
        for x in ABIL:
            if re.search(r'(?<![\w-])'+re.escape(x)+r'(?![\w-])',rest): aa.append(x); rest=rest.replace(x,' ')
        for n in sp: rest=rest.replace(n,' ')
        for y in TYPES:
            if re.search(r'\b'+y+r'\b',rest) and y not in ts and y not in skip: bad.append(('type',y,s[:90]))
        for x in aa:
            if x not in as_ and x not in skip: bad.append(('ability',x,s[:90]))
    return bad
def evaluate(iid,a):
    """-> (status, reasons) status in correct|false|non_answer"""
    it=K[iid]; t=a['final_text']; ty=it['claim_type']; gt=it['claims'][0]['ground_truth']; kind=it['claims'][0]['kind']; why=[]
    if not t.strip(): return 'non_answer',['empty']
    if ty in('typing','ability','ability_form','item','legality'):
        key={'typing':'has_type','ability':'has_ability','ability_form':'has_ability','item':'legal','legality':'legal'}[ty]
        v=yn(t)
        if v is None: return 'non_answer',['no yes/no']
        if v!=gt[key]: why.append('asked proposition wrong')
        why+=[f"extra {x[0]} {x[1]}" for x in extras(it,t)]
    elif ty=='move_static':
        m=MV[gt['id']]; want={'category':m['category'],'base_power':str(m['basePower']),'move_type':m['type']}[kind]
        if want.lower() not in t.lower(): why.append('asked value missing')
        for y in TYPES:
            if re.search(r'\b'+y+r'\b',t) and y!=m['type']: why.append(f'wrong type {y}')
        for c in('Physical','Special','Status'):
            if re.search(r'\b'+c+r'\b',t,re.I) and c!=m['category'] and kind!='category' or (kind=='category' and re.search(r'\b'+c+r'\b',t,re.I) and c!=m['category'] and not re.search(r'not (a |an )?'+c,t,re.I)): why.append(f'wrong category {c}')
        for n in re.findall(r'\b\d+\b',t):
            if int(n)!=m['basePower']: why.append(f'wrong number {n}')
    elif ty=='speed':
        s1,s2=gt['s1'],gt['s2']
        if not {str(gt['spe1_jolly32']),str(gt['spe2_timid32'])}<=set(re.findall(r'\d+',t)): why.append('stat values missing/wrong')
        ss=[x for x in sents(t) if re.search(r'faster|outspeed|slower|tie',x,re.I)]
        if not ss: return 'non_answer',['no verdict sentence']
        s=ss[-1]; low=s.lower(); i1,i2=s.find(s1),s.find(s2)
        fst=s1 if (i1>=0 and (i2<0 or i1<i2)) else s2
        neg=bool(re.search(r'slower|does not outspeed|doesn.t outspeed|not faster',low))
        w=(s2 if fst==s1 else s1) if neg else fst
        if w!=(s1 if gt['s1_outspeeds'] else s2): why.append('winner wrong')
    elif ty=='damage':
        m=re.search(r'\b(yes|no)\b',first(t).lower()) or re.search(r'\b(yes|no)\b',t.lower())
        if not m: return 'non_answer',['no yes/no']
        if (m.group(1)=='yes')!=gt['guaranteed_ko']: why.append('yes/no wrong')
        k=gt['rolls_ko_of_16']
        for n in re.findall(r'(\d+)\s*(?:out of|of)\s*(?:the\s*)?(?:possible\s*)?16',t):
            if int(n)!=k: why.append(f'roll count {n} vs {k}')
        for p in re.findall(r'(\d+(?:\.\d+)?)\s*%\s*(?:chance(?! to)|of the (?:damage )?rolls)',t):
            if abs(float(p)-100*k/16)>3.125: why.append(f'chance {p}% vs {100*k/16}')
    elif ty in('usage','usage_showdown'):
        listed=re.findall(r'^\s*\d+\.\s*\**([^*(\n:]+?)\**\s*(?:\s-\s|[(:]|$)',t,re.M)
        keyset=set(gt.get('common_items',[]))|set(gt.get('teammates',[]))
        for n in listed:
            if n.strip() not in keyset: why.append(f'listed non-key member {n.strip()}')
        if not listed: return 'non_answer',['no list parsed']
        for c in a['tool_calls']:
            rows=c['result'].get('rows') or c['result'].get('items') or []
            for r in rows:
                pct=r.get('conditional_pct',r.get('pct'))
                if pct is None: continue
                mm=re.search(re.escape(r['name'])+r'(?![\w-])\**\s*(?:-\s*|[(:]\s*)+(\d+(?:\.\d+)?)%',t)
                d=len(mm.group(1).split('.')[1]) if mm and '.' in mm.group(1) else 0
                if mm and abs(float(mm.group(1))-pct)>0.5*10**-d+1e-9: why.append(f"pct for {r['name']} {mm.group(1)} vs tool {pct}")
    return ('false' if why else 'correct'),why
if __name__=='__main__':
    import collections
    A={r['id']:r for r in map(json.loads,open('dev1/answers.jsonl'))}
    c=collections.Counter(); tool_backed_correct={}
    for iid,a in A.items():
        st,why=evaluate(iid,a); c[(bool(a['tool_calls']),st)]+=1
        if a['tool_calls'] and st=='correct': tool_backed_correct.setdefault(K[iid]['claim_type'],[]).append(iid)
    print(sorted(c.items(),key=str)); print({k:v[:2] for k,v in tool_backed_correct.items()})
    for iid,a in A.items():
        st,why=evaluate(iid,a)
        if a['tool_calls'] and st!='correct': print(iid,st,why[:3])

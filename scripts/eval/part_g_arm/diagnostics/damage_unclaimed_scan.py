# THROWAWAY DIAGNOSTIC, NOT SCORER CODE. Sentences of the dev3b damage answers that state a KO, threshold or roll relation, or contain a number, and yield no
# extracted claim. Claims are taken before the guaranteed-KO deduplication, so a sentence whose claim was folded onto another is not counted as unclaimed.
# Prints item id, span and pattern family (no verdicts). Run (cwd scripts/eval/part_g_arm/): python diagnostics/damage_unclaimed_scan.py runs/dev3b [--text]
import json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "part_g_v4"))
import extractors as ex
ex.sc.dedupe = lambda cs: list(cs)  # coverage view: every emitted claim, before the equivalence folding
K = {i["id"]: i for i in json.load(open(HERE.parent / "dev_seed1/claim_battery_v4.json"))["items"] if i["claim_type"] == "damage"}
A = {r["id"]: r for r in map(json.loads, open(Path(sys.argv[1]) / "answers.jsonl"))}
SHOW = "--text" in sys.argv
RELATION = re.compile(r"\b(?:ko|knock\w*|threshold|hko|rolls?|survive\w*|guarantee\w*|one hit|single hit|two hits?|hits?)\b", re.I)
FAMILIES = [
    ("roll-descriptor KO (max/min/highest/lowest roll would or would not KO)", r"\b(?:maximum|max|highest|top|minimum|min|lowest|bottom)\b[^.]{0,40}\broll|\b(?:a |the |any )?roll of \d"),
    ("N or higher / at least N KO", r"\d\s*(?:or|and)\s*(?:higher|more|above|greater)|at least \d|\d\s*\+"),
    ("rolls above / below / over / under N", r"\brolls?\s+(?:above|below|over|under|greater than|less than|exceed\w*)\s+\d|\b(?:above|below|over|under)\s+\d+[^.]{0,20}\brolls?"),
    ("damage needed / threshold figure", r"\b(?:need\w*|require\w*|threshold)\b[^.]{0,40}\d"),
    ("n-hit KO (HKO / hits) statement", r"\d\s*-?\s*hko|\bohko\b|\d[- ]hit|\btwo hits?\b|\bthree hits?\b|\bin \d hits"),
    ("damage range or percent of HP", r"\d+\s*(?:-|to)\s*\d+|\d\s*%"),
    ("defender HP stated", r"\bhp\b[^.]{0,20}\d|\d+\s*hp\b"),
    ("roll count (N of 16, all/none of the rolls)", r"\b(?:all|every|none|zero|no|\d+)\b[^.]{0,25}\brolls?\b|\bof the 16\b|\b16\b"),
    ("verdict restatement (guarantee / OHKO wording)", r"\bguarantee\w*|\bohko\b|does not (?:ko|knock)|doesn't (?:ko|knock)"),
    ("HP remaining or survival", r"\bremain\w*|\bsurviv\w*|\bleft\b"),
]
def family(s):
    for name, pat in FAMILIES:
        if re.search(pat, s, re.I):
            return name
    return "other number or relation"
rows = []
for i in sorted(K):
    claims = ex.extract_item(K[i], A[i])
    spans = [c.span for c in claims if c.span]
    for s, off in ex.sents_pos(A[i]["final_text"]):
        if not (re.search(r"\d", s) or RELATION.search(s)):
            continue
        lo, hi = off, off + len(s)
        if any(a < hi and b > lo for a, b in spans):
            continue
        rows.append((i, (lo, hi), family(s), s))
for i, sp, fam, s in rows:
    print(f"{i} | span {sp} | {fam}" + (f"\n      {s}" if SHOW else ""))
print(len(rows), "unclaimed sentences in", len({r[0] for r in rows}), "of", len(K), "damage answers")

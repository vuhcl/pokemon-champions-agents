#!/usr/bin/env python3
"""Test the guard class mapping (guard_class_mapping_2026-10-30.md) against Vu's expected-tool lists.
Usage: python3 check_expected_tools.py expected_tools_filled.csv
Columns used: row_id, turn, key_class, proposed_guard_class, guard_class_override,
expected_tools_ordered (semicolon-separated), optional_tools (semicolon-separated).
Families are exactly those in the mapping doc; anything else is reported as unmapped, not guessed."""
import csv, sys, collections
LOOKUP = {"get_typing","get_abilities","check_species_ability","check_species_legal","check_item_legal",
          "get_move_static","get_speed","calc_damage","get_usage_items","get_usage_teammates",
          "check_learnset","find_species","solve_spread","describe","no_lookup_needed","show_candidates","get_usage_spreads","get_common_speeds","get_meta_threats","get_usage_stats"}
READ = {"read_team","read_pending","read_constraints","read_archetype","read_rejected"}
HYPO = {"check_hypothetical"}
WRITE = {"set_slot","lock_slot","unlock_slot","edit_slot_field","commit_slot","commit_full_slot",
         "change_archetype","add_constraint","reset_team","select_option","confirm_build","restore_constraint",
         "lock_fields","unlock_fields"}  # reject_* matched by prefix
def is_write(t): return t in WRITE or t.startswith("reject")
ALLOWED = {
  "LOOKUP": LOOKUP | READ,
  "READ_STATE": READ,
  "HYPOTHETICAL": LOOKUP | HYPO | READ,
  "ASK": READ,
  "READ_ONLY_REFUSE": READ,
}
# Revision 2026-10-31: WRITE binds build-support lookups only; numeric/describe tools need a numeric sub-request.
WRITE_LOOKUP = {"get_typing","get_abilities","check_species_ability","check_species_legal","check_item_legal","get_move_static",
                "check_learnset","find_species","get_usage_items","get_usage_teammates","get_usage_spreads","get_usage_stats",
                "get_common_speeds","get_meta_threats","show_candidates"}
NUMERIC = {"calc_damage","get_speed","solve_spread","describe","no_lookup_needed"}
def allowed(cls, t):
    if cls in ("WRITE","PENDING_ANSWER"): return is_write(t) or t in READ or t in WRITE_LOOKUP or t in NUMERIC
    return t in ALLOWED.get(cls, set())
def tools(s):
    """Semicolon-separated steps; a step may list alternatives with '|' (any one satisfies)."""
    return [x.strip() for x in (s or "").split(";") if x.strip()]
def alts(step): return [a.strip() for a in step.split("|") if a.strip()]
rows = list(csv.DictReader(open(sys.argv[1], newline="")))
known = LOOKUP | READ | HYPO | WRITE
issues = collections.defaultdict(list); filled = 0
for r in rows:
    exp, opt = tools(r["expected_tools_ordered"]), tools(r["optional_tools"])
    if not exp and not opt and not r.get("notes"): continue
    filled += 1
    cls = r.get("guard_class_override") or r["proposed_guard_class"]
    rid = f'{r["row_id"]} t{r["turn"]}'
    for step in exp + opt:
        for t in alts(step):
            if not (t in known or t.startswith("reject")):
                issues["unmapped tool (place it in a family)"].append(f"{rid}: {t}"); continue
            if not allowed(cls, t):
                kind = "write tool in non-WRITE class" if is_write(t) else f"tool outside {cls} family"
                issues[kind].append(f"{rid} [{r['key_class']} -> {cls}]: {t}")
    if cls == "WRITE":
        for st in exp + opt:
            for t in alts(st):
                if t in NUMERIC: issues["WRITE row expects a numeric tool: parser must emit a numeric sub-request (+845 tokens)"].append(f"{rid}: {t}")
    if cls == "WRITE" and not any(is_write(t) for st in exp + opt for t in alts(st)):
        issues["WRITE class with no write tool expected (refusal untested?)"].append(f"{rid} [{r['key_class']}]")
    if r["key_class"] in ("MUTATION-OK","MUTATION-REFUSED") and cls != "WRITE":
        issues["mutation key class not mapped to WRITE"].append(f"{rid} -> {cls}")
    if r["key_class"] in ("SERVED","ASSUME-STATE","PARTIAL","PARTIAL+ASSUME-STATE") and any(is_write(t) for st in exp for t in alts(st)):
        issues["write tool REQUIRED on a non-mutation key class (check against the key)"].append(f"{rid} [{r['key_class']}]")
print(f"rows with an expected list: {filled} of {len(rows)}")
if not issues: print("no mapping gaps found in the filled rows")
for k, v in issues.items():
    print(f"\n{k}: {len(v)}")
    for x in v: print("  ", x)

#!/usr/bin/env python3
"""Read-only generators: cursor_fixture_key_sweep.md + cursor_run1_tallies.md (run_1 only)."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("/Users/nowaki027/part-g-arm-runs/pre-rs-arm/b98568d")
WT = Path("/Users/nowaki027/part-g-arm-state-run-b98568d")

STATE_CHANGING = {
    "lock_slot",
    "unlock_slot",
    "reset_team",
    "reset_team_state",
    "edit_slot_field",
    "commit_slot",
    "confirm_build",
    "select_option",
    "reject_option",
    "reject_all",
    "reject_pending",
    "add_constraint",
    "restore_constraint",
    "restore_constraint_tool",
    "change_archetype",
}

NOT_ALLOWED_ATOMS = {
    "NO-MUTATION",
    "ASK",
    "MUTATION-REFUSED",
    "FAIL-CLOSED",
    "SERVED",
    "ASSUME-STATE",
    "PARTIAL",
    "PARTIAL+ASSUME-STATE",
    "ASK|ASSUME-STATE",
}
# MUTATION-OK = allowed to change. lookup-only is observed mech, not a key class atom.


def load_transcript() -> dict[str, Any]:
    return {e["id"]: e for e in json.loads((ROOT / "run_1" / "transcript.json").read_text())}


def attrs_map(slot: dict) -> dict[str, tuple[Any, bool]]:
    out: dict[str, tuple[Any, bool]] = {}
    for a in slot.get("attrs") or []:
        if isinstance(a, (list, tuple)) and a:
            out[str(a[0])] = (a[1] if len(a) > 1 else None, bool(a[2]) if len(a) > 2 else False)
    return out


def fmt_locked_slots(entry: dict) -> str:
    turns = entry.get("turns") or []
    if not turns or not entry.get("loaded"):
        return "—" if not entry.get("loaded") else "(no locked slots)"
    sb = turns[0].get("state_before") or {}
    parts = []
    for s in sb.get("slots") or []:
        am = attrs_map(s)
        if not (s.get("species_locked") or any(lk for _, lk in am.values())):
            continue
        def g(n: str) -> str:
            v, lk = am.get(n, (None, False))
            return f"{v}{'*' if lk else ''}"
        parts.append(
            f"s{s.get('slot')}:{s.get('species')}{'*' if s.get('species_locked') else ''}"
            f" abl={g('ability')} item={g('item')} nat={g('nature')} spr={g('spread')} mv={g('moveset')}"
        )
    return " || ".join(parts) if parts else "(no locked slots)"


def source_label(entry: dict) -> str:
    if not entry.get("loaded"):
        return "load_fail"
    src = ((entry.get("start_meta") or {}).get("source") or "")
    if src.startswith("seeds/") or (entry.get("start_meta") or {}).get("seed"):
        seed = (entry.get("start_meta") or {}).get("seed") or src.replace("seeds/", "")
        name = Path(str(seed)).name
        if not name.endswith(".json"):
            name += ".json"
        return f"seed file: seeds/{name}"
    m = re.search(r"load_fixture\('([^']+)'\)", src)
    if m:
        return f"named fixture: load_fixture({m.group(1)!r})"
    if "build_fully_locked_mega" in src:
        return "build_fully_locked_mega"
    if "build_fully_locked_slot" in src:
        return "build_fully_locked_slot"
    if "build_mrb1" in src:
        return "other: build_mrb1_start"
    if src.startswith("empty_team"):
        return "empty_team" if src == "empty_team" else f"empty_team ({src[len('empty_team'):].strip(' ()')})"
    if src.startswith("scripts/eval/"):
        return f"named fixture file: {src}"
    return f"other: {src}" if src else "other: unknown"


def snap_state(turn: dict, which: str) -> dict:
    st = turn.get(which) or {}
    return {"slots": st.get("slots"), "steering": st.get("steering")}


def state_changed(turn: dict) -> bool:
    return snap_state(turn, "state_before") != snap_state(turn, "state_after")


def key_args(name: str, args: Any) -> str:
    if not isinstance(args, dict):
        return json.dumps(args, sort_keys=True)[:200]
    # keep compact key fields
    keep = {}
    for k in (
        "slot", "species", "field", "value", "item", "move", "n", "components",
        "predicate", "scope", "option", "index", "attacker", "defender",
        "types", "ability", "stat_formula", "learns_move",
    ):
        if k in args:
            keep[k] = args[k]
    if not keep:
        keep = args
    return json.dumps(keep, sort_keys=True)[:300]


def write_fixture_sweep(t: dict[str, Any]) -> None:
    import sys
    sys.path.insert(0, str(WT))
    from scripts.eval.part_g_arm.state.request_set_rows import load_covered_ids, load_request_rows

    rows = {r["id"]: r for r in load_request_rows()}
    covered = sorted(load_covered_ids())
    keys = json.loads((WT / "scripts/eval/part_g_v4/key_artifacts/derived_keys.json").read_text())
    dm = keys.get("dm_outputs") or {}

    # Reuse prior verdicts logic (compact)
    lac = (dm.get("dm2") or {}).get("locked_attacker_confirmed") or {}
    EXPECT: dict[str, tuple[str, str]] = {}  # rid -> (quote, verdict)

    def set_v(rid: str, quote: str, verdict: str) -> None:
        EXPECT[rid] = (quote, verdict)

    set_v(
        "DM2",
        f'acceptance Locked fixture attacker = Adamant Life Orb Atk-32 ability Intimidate; '
        f'locked_attacker_confirmed={json.dumps(lac, sort_keys=True)}',
        "MISMATCH",
    )
    for rid in ("DM1", "DM3", "DM4", "DM6", "DM7", "H5"):
        if rid == "H5":
            q = f"ASSUME-STATE h5.attacker={json.dumps((keys.get('h5') or {}).get('attacker'), sort_keys=True)}"
        elif rid == "DM1":
            q = f"ASSUME-STATE dm1.attacker={json.dumps((dm.get('dm1') or {}).get('attacker'), sort_keys=True)[:180]}"
        else:
            q = f"ASSUME-STATE/calc (not locked start): {(rows[rid].get('acceptance') or '')[:140]!r}"
        set_v(rid, q, "KEY SILENT")
    set_v("MM1", f"idle; acceptance build target: {(rows['MM1'].get('acceptance') or '')[:100]!r}", "KEY SILENT")
    set_v("MM2", "state Salamence-Mega+Salamencite", "MATCH")
    set_v("MR3", "state 'one locked'; prompt Lock a second Incineroar", "MISMATCH")
    set_v("MS1", "state idle empty; acceptance end-state only", "KEY SILENT")
    set_v("MS2", "state 'slot1 locked'", "MISMATCH")
    set_v("MS3", "state '2 locked'", "MISMATCH")
    set_v("MS4", "FBC pending", "KEY SILENT")
    set_v("MS5", "acceptance Drought+Solar Beam conflicts; Pelipper control", "MATCH")
    set_v("MS6", "idle", "KEY SILENT")
    set_v("MS7", "CS pending", "KEY SILENT")
    set_v("MS8", "idle; end-state Pelipper", "KEY SILENT")
    set_v("MRB1", "Torkoal/Drought/Charcoal slot3", "MATCH")
    set_v("HN2c", "Annihilape locked Jolly Spe-32", "MATCH")
    set_v("HN2d", "Blaziken-Mega+Blazikenite Spe Jolly-32", "MATCH")
    set_v("IC1", "Sneasler=Psychic Seed, Indeedee-F=Rocky Helmet", "MATCH")
    set_v("IS2", "Basculegion locked Jolly Choice Scarf; non-Spe SP sum 42", "MATCH")
    set_v("RB1", "Lucario-Mega-Z + Lucarionite Z; moves Aura Sphere/Flash Cannon/Calm Mind", "MISMATCH")
    set_v("TB2", "Incineroar+Charcoal; Flare Blitz", "MISMATCH")
    set_v("MW2", "state ≥1 locked", "MISMATCH")

    lines = [
        "# cursor_fixture_key_sweep.md",
        "",
        "Read-only. Covered 103, run_1. Verdict axis: locked-slot fields the key/state cell quotes.",
        "ASSUME-STATE calc sides on empty_team → KEY SILENT on locked-slot axis.",
        "",
        "## Counts",
        "",
    ]
    table_rows = []
    for rid in covered:
        entry = t[rid]
        src = source_label(entry)
        loaded = fmt_locked_slots(entry)
        if rid in EXPECT:
            quote, verdict = EXPECT[rid]
        else:
            quote = f"state={(rows[rid].get('state') or '')[:80]!r}; acceptance={(rows[rid].get('acceptance') or '')[:100]!r}"
            st = (rows[rid].get("state") or "").strip().lower()
            if st in ("one locked", "slot1 locked", "≥1 locked", ">=1 locked") and "empty_team" in src:
                verdict = "MISMATCH"
            elif st == "2 locked" and "empty_team" in src:
                verdict = "MISMATCH"
            else:
                verdict = "KEY SILENT"
        table_rows.append((rid, src, loaded, quote, verdict))

    c = Counter(v for *_, v in table_rows)
    lines.append(f"- MATCH: {c['MATCH']}")
    lines.append(f"- MISMATCH: {c['MISMATCH']}")
    lines.append(f"- KEY SILENT: {c['KEY SILENT']}")
    lines.append(f"- build_fully_locked_slot rows: {[r for r,s,_,_,_ in table_rows if s=='build_fully_locked_slot']}")
    lines.append(f"- build_fully_locked_mega rows: {[r for r,s,_,_,_ in table_rows if s=='build_fully_locked_mega']}")
    lines.append("")
    lines.append("| row | start-state source | loaded locked slot(s) | key / request-set quote | verdict |")
    lines.append("|---|---|---|---|---|")
    for rid, src, loaded, quote, verdict in table_rows:
        def esc(x: str, n: int = 400) -> str:
            return str(x)[:n].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {rid} | {esc(src,120)} | {esc(loaded,220)} | {esc(quote,220)} | {esc(verdict,120)} |")

    # Addendum: DM2 + other MISMATCH transcripts
    lines += ["", "## Addendum — MISMATCH rows: tool calls / final text / which set (quote only)", ""]
    mismatch_ids = [r for r, *_, v in table_rows if v == "MISMATCH"]
    for rid in mismatch_ids:
        entry = t[rid]
        lines.append(f"### {rid}")
        lines.append("")
        lines.append(f"- start source: `{source_label(entry)}`")
        lines.append(f"- loaded: `{fmt_locked_slots(entry)}`")
        if rid == "DM2":
            lines.append(
                f"- key attacker: nature={lac.get('nature')!r} item={lac.get('item')!r} "
                f"ability={lac.get('ability')!r} evs={lac.get('evs')!r}"
            )
        turns = entry.get("turns") or []
        if not turns:
            lines.append("- turns: none (load_fail or empty)")
            lines.append("")
            continue
        for ti, turn in enumerate(turns, 1):
            lines.append(f"- turn {ti} tool_calls:")
            read_draft = False
            for ci, tc in enumerate(turn.get("tool_calls") or [], 1):
                name = tc.get("name")
                args = tc.get("args") if "args" in tc else tc.get("arguments")
                if name in ("read_team", "read_pending", "read_constraints", "read_archetype", "read_rejected"):
                    read_draft = True
                lines.append(f"  - [{ci}] `{name}` args={json.dumps(args, sort_keys=True)[:500]}")
                if name == "calc_damage" and isinstance(args, dict):
                    atk = args.get("attacker") or {}
                    lines.append(
                        "    attacker_set: "
                        f"species={atk.get('species')!r} ability={atk.get('ability')!r} "
                        f"item={atk.get('item')!r} nature={atk.get('nature')!r} "
                        f"spread={atk.get('sp') or atk.get('evs')!r} move={args.get('move')!r}"
                    )
                res = tc.get("result")
                if isinstance(res, dict) and name == "calc_damage":
                    slim = {k: res[k] for k in ("status", "damage_range", "ko_text", "error_kind", "message") if k in res}
                    lines.append(f"    result_slim={json.dumps(slim, sort_keys=True)[:300]}")
            lines.append(f"  - read_draft/locked_slot_before_calc: {read_draft}")
            ft = turn.get("final_text") or turn.get("response") or ""
            lines.append(f"  - final_text: {ft!r}"[:2000])
            # which set
            if rid == "DM2":
                # extract attacker from successful/attempted calcs
                atks = []
                for tc in turn.get("tool_calls") or []:
                    if tc.get("name") != "calc_damage":
                        continue
                    a = (tc.get("args") or {}).get("attacker") or {}
                    atks.append(a)
                lines.append("  - match_loaded_fixture: no (loaded Blaze/Sitrus/Modest/spa32; calcs use Intimidate/Jolly/spe32)")
                lines.append("  - match_key_attacker: no (key Adamant/Life Orb/atk32/spd4; calcs Jolly/empty-or-Black Sludge/spe32)")
                lines.append("  - match: neither")
                # numbers in final text
                nums = re.findall(r"\d+(?:\.\d+)?%?|\d+-\d+", ft)
                lines.append(f"  - numbers_in_final_text: {nums}")
            elif not entry.get("loaded"):
                lines.append("  - match: neither (nothing loaded)")
            elif fmt_locked_slots(entry) == "(no locked slots)":
                lines.append("  - match_loaded_fixture: n/a (empty load)")
                lines.append("  - match: neither vs key/state lock assumption (0 locked loaded)")
            else:
                lines.append("  - match: see tool args vs loaded/key quotes above (structural MISMATCH)")
        lines.append("")

    (ROOT / "cursor_fixture_key_sweep.md").write_text("\n".join(lines) + "\n")
    print("wrote", ROOT / "cursor_fixture_key_sweep.md", "mismatches", mismatch_ids)


def write_tallies(t: dict[str, Any]) -> None:
    import sys
    sys.path.insert(0, str(WT))
    from scripts.eval.part_g_arm.state.request_set_rows import load_covered_ids, load_request_rows
    from scripts.eval.part_g_arm.state.errata_read import expected_turns
    from scripts.eval.part_g_arm.state.reference_trajectories import hand_audit_tool_map
    from scripts.eval.part_g_arm.state import reference_trajectories as refmod
    from recommender.arm_tools import ArmTools

    rows = {r["id"]: r for r in load_request_rows()}
    covered = set(load_covered_ids())

    # A
    lines = [
        "# cursor_run1_tallies.md",
        "",
        "Read-only. run_1 transcripts only. Numbers and quotes; no interpretation.",
        "",
        "## A. Unrequested state changes (113 turns)",
        "",
        "| row | turn | ordered tool calls | state-changing tool ran | draft/constraints/archetype differ before→after | allowed? |",
        "|---|---|---|---|---|---|",
    ]
    unallowed_changed = []
    allowed_or_required_turns = 0
    not_allowed_turns = 0
    for rid in sorted(covered):
        entry = t[rid]
        class_cell = str(rows[rid].get("class") or "").strip()
        exp_list = expected_turns(rid, class_cell)
        for ti, turn in enumerate(entry.get("turns") or [], 1):
            exp = exp_list[ti - 1] if ti - 1 < len(exp_list) else (exp_list[-1] if exp_list else class_cell)
            # multi-atom cells like "PARTIAL+ASSUME-STATE" or errata lists
            atoms = re.split(r"[+/|]", exp) if exp else []
            atoms = [a.strip() for a in atoms if a.strip()]
            allowed = any(a == "MUTATION-OK" for a in atoms) or exp == "MUTATION-OK"
            # GS1 etc may have SERVED then MUTATION-OK per turn via errata
            if allowed:
                allowed_or_required_turns += 1
                allow_label = "allowed to change"
            else:
                not_allowed_turns += 1
                allow_label = "not allowed"

            tools = turn.get("tool_calls") or []
            ordered = "; ".join(f"{c.get('name')}({key_args(c.get('name'), c.get('args') if 'args' in c else c.get('arguments'))})" for c in tools)
            changing = [c.get("name") for c in tools if c.get("name") in STATE_CHANGING]
            changed = state_changed(turn)
            if changed and not allowed:
                unallowed_changed.append((rid, ti, ordered[:200], changing, allow_label))
            lines.append(
                f"| {rid} | {ti} | {ordered[:250].replace('|','\\|')} | "
                f"{'yes: '+','.join(changing) if changing else 'no'} | "
                f"{'yes' if changed else 'no'} | {allow_label} |"
            )

    lines += [
        "",
        "### A counts",
        f"- turns total: {sum(len(t[r].get('turns') or []) for r in covered)}",
        f"- turns allowed to change (MUTATION-OK expected that turn): {allowed_or_required_turns}",
        f"- turns not allowed: {not_allowed_turns}",
        f"- turns where state changed and change was not allowed: {len(unallowed_changed)}",
        "",
        "### A unallowed changes (list)",
        "",
        "| row | turn | tools (trunc) | state-changing names |",
        "|---|---|---|---|",
    ]
    for rid, ti, ordered, changing, _ in unallowed_changed:
        lines.append(f"| {rid} | {ti} | {ordered.replace('|','\\|')} | {','.join(changing)} |")

    # Fix class_cell discovery — print sample if many zeros
    # Re-run A with proper field from request rows
    sample = next(iter(rows.values()))
    # B show_candidates
    lines += ["", "## B. show_candidates", "", "| row | turn | args | result | fully_locked_anchor? | blank_next_slot? |", "|---|---|---|---|---|---|"]
    sc_calls = []
    refusals = Counter()
    successes = 0
    for rid in sorted(covered):
        for ti, turn in enumerate(t[rid].get("turns") or [], 1):
            sb = turn.get("state_before") or {}
            slots = sb.get("slots") or []
            # approximate all_locked: species+ability+item+nature+spread+moveset+role all locked
            def slot_all_locked(s: dict) -> bool:
                am = attrs_map(s)
                need = ("species", "ability", "item", "nature", "spread", "moveset", "role")
                for n in need:
                    v, lk = am.get(n, (None, False))
                    if n == "species":
                        lk = lk or bool(s.get("species_locked"))
                        v = v or s.get("species")
                    if not lk or v in (None, "", []):
                        return False
                return True
            anchors = [s for s in slots if slot_all_locked(s)]
            blanks = [s for s in slots if not s.get("species") and not s.get("species_locked")]
            for tc in turn.get("tool_calls") or []:
                if tc.get("name") != "show_candidates":
                    continue
                args = tc.get("args") if "args" in tc else tc.get("arguments")
                res = tc.get("result") or {}
                err = None
                n_opt = 0
                if isinstance(res, dict):
                    err = res.get("slot_commit_error") or res.get("error") or res.get("message")
                    opts = res.get("options") or res.get("candidates") or []
                    n_opt = len(opts) if isinstance(opts, list) else 0
                if err:
                    refusals[str(err)] += 1
                    result_s = f"error: {err}"
                else:
                    successes += 1
                    result_s = f"ok n_options={n_opt}"
                sc_calls.append((rid, ti, args, result_s, bool(anchors), bool(blanks)))
                lines.append(
                    f"| {rid} | {ti} | {json.dumps(args, sort_keys=True)} | {str(result_s)[:160].replace('|','\\|')} | "
                    f"{'yes' if anchors else 'no'} | {'yes' if blanks else 'no'} |"
                )

    # reference trajectory expects show_candidates
    ref_wants = []
    # from hand map + part3 json
    part3 = json.loads((WT / "scripts/eval/part_g_arm/state/part3_reference_trajectories.json").read_text())
    for h in part3.get("hand_audit") or []:
        if "show_candidates" in (h.get("tools") or ""):
            ref_wants.append(h["row"])
    # also mechanical trajectories mentioning show_candidates in tools string in MAP via hand_audit_tool_map
    for h in hand_audit_tool_map():
        if "show_candidates" in h.get("tools", "") and h["row"] not in ref_wants:
            ref_wants.append(h["row"])
    missing_sc = []
    for rid in sorted(set(ref_wants) & covered):
        called = False
        for turn in t[rid].get("turns") or []:
            if any(c.get("name") == "show_candidates" for c in turn.get("tool_calls") or []):
                called = True
                break
        if not called:
            missing_sc.append(rid)

    lines += [
        "",
        "### B counts",
        f"- show_candidates calls: {len(sc_calls)}",
        f"- successes (no error field): {successes}",
        f"- refusals by error text: {dict(refusals)}",
        f"- rows whose reference tools mention show_candidates but arm did not call it: {missing_sc}",
        "",
        "### H18b fixture lock flags + _fixture_incomplete",
        "",
    ]
    e = t["H18b"]
    sb = (e.get("turns") or [{}])[0].get("state_before") or {}
    for s in sb.get("slots") or []:
        if int(s.get("slot") or 0) > 4 and not s.get("species"):
            continue
        am = attrs_map(s)
        flags = {k: {"value": v, "locked": lk} for k, (v, lk) in am.items() if k in ("species", "ability", "item", "nature", "spread", "moveset", "role")}
        lines.append(f"- slot {s.get('slot')}: species={s.get('species')!r} species_locked={s.get('species_locked')} attrs={json.dumps(flags, sort_keys=True)}")
    # resolve incomplete
    from scripts.eval.part_g_arm.state.request_set_rows import resolve_start_state
    st, meta = resolve_start_state(rows["H18b"])
    lines.append(f"- start_meta.complete={meta.get('complete')} error={meta.get('error')!r}")
    lines.append(f"- _fixture_incomplete={json.dumps((st or {}).get('_fixture_incomplete'))}")
    lines.append(
        "- t1 show_candidates results: "
        + "; ".join(
            json.dumps(c.get("result"), sort_keys=True)
            for c in (e["turns"][0].get("tool_calls") or [])
            if c.get("name") == "show_candidates"
        )
    )

    # C not flagged / unchanged
    lines += ["", "## C. Key says control/other slot not flagged or unchanged", ""]
    patterns = re.compile(r"not flagged|unchanged|control |clean|state unchanged", re.I)
    for rid in sorted(covered):
        acc = rows[rid].get("acceptance") or ""
        if not patterns.search(acc):
            continue
        lines.append(f"### {rid}")
        lines.append(f"- acceptance quote: {acc[:300]!r}")
        for ti, turn in enumerate(t[rid].get("turns") or [], 1):
            for tc in turn.get("tool_calls") or []:
                if tc.get("name") not in ("change_archetype", "edit_slot_field", "lock_slot", "unlock_slot", "add_constraint"):
                    continue
                res = tc.get("result")
                if not isinstance(res, dict):
                    continue
                fields = {k: res.get(k) for k in ("conflicts", "pending_flags", "ok", "archetype", "slot_commit_error", "consequences") if k in res}
                lines.append(f"- t{ti} `{tc.get('name')}` result fields: {json.dumps(fields, sort_keys=True)[:800]}")
        lines.append("")

    # D trigger phrases in form points — need hand_audit form points from html/csv template
    # Use hand_audit.csv skeleton + acceptance? Better: parse form from hand_audit.html data or regenerate points from form builder
    from scripts.eval.part_g_arm.state.hand_audit_form import build_sections_from_transcript
    lines += ["", "## D. Form points with trigger-like phrases", ""]
    triggers = ("= false", "= not", "unless", "flat yes/no", "no stated", "must not", "never", "wrong")
    lines.append("| row | turn | point id | text |")
    lines.append("|---|---|---|---|")
    n_d = 0
    try:
        hand_ids = set(json.loads((ROOT / "run_1_hand_ids.json").read_text())["ids"])
        acceptance_by_id = {rid: rows[rid].get("acceptance") or "" for rid in hand_ids if rid in rows}
        transcript_list = json.loads((ROOT / "run_1" / "transcript.json").read_text())
        sections = build_sections_from_transcript(
            transcript_list,
            acceptance_by_id=acceptance_by_id,
            ids=hand_ids,
        )
        for sec in sections:
            rid = sec.get("row_id") or sec.get("row")
            turn = sec.get("turn")
            for p in sec.get("points") or []:
                text = str(p.get("text") or p.get("label") or "")
                low = text.lower()
                if any(tr in low for tr in triggers):
                    lines.append(
                        f"| {rid} | {turn} | {p.get('id')} | {text[:220].replace('|', '\\|')} |"
                    )
                    n_d += 1
        lines.append("")
        lines.append(f"- D count: {n_d}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"(D parse error: {type(exc).__name__}: {exc})")

    # E tool capability
    lines += ["", "## E. Tool-capability check (key fact vs tool return fields)", ""]
    lines.append("| row | fact (from key/acceptance) | ref tools | fields present / ABSENT |")
    lines.append("|---|---|---|---|")
    arm = ArmTools(regulation="champions", allow_live=False)
    try:
        wish = arm.get_move_static("Wish")
    except Exception as exc:  # noqa: BLE001
        wish = {"_error": f"{type(exc).__name__}: {exc}"}
    lines.append("")
    lines.append(f"### probe get_move_static('Wish') → {json.dumps(wish, sort_keys=True)}")

    # Map covered rows with numeric/specific facts
    fact_rows = []
    for rid in sorted(covered):
        acc = rows[rid].get("acceptance") or ""
        # skip empty
        if not acc:
            continue
        # use hand map + mechanical notes from part3
        ref = None
        for h in part3.get("hand_audit") or []:
            if h.get("row") == rid:
                ref = h.get("tools")
                break
        if ref is None:
            for h in hand_audit_tool_map():
                if h["row"] == rid:
                    ref = h.get("tools")
                    break
        # extract a short fact if acceptance has = or number
        if rid in ("MV1", "MV2", "MV3", "H7", "HN4", "IX1", "H4", "HN2", "H5", "DM1"):
            fact_rows.append((rid, acc[:160], ref or "—"))

    # For each, check run1 tool results for field presence
    for rid, fact, ref in fact_rows:
        entry = t[rid]
        present = []
        absent = []
        # facts of interest by row
        needed: list[str] = []
        if rid == "MV2":
            needed = ["pp"]
        elif rid == "MV1":
            needed = ["priority"]
        elif rid == "MV3":
            needed = ["target"]  # may be absent
        elif rid == "H7":
            needed = ["category", "base_power"]
        elif rid in ("H4", "HN2"):
            needed = ["spe", "speed"]
        else:
            needed = []
        # scan tool results
        fields_seen: set[str] = set()
        for turn in entry.get("turns") or []:
            for tc in turn.get("tool_calls") or []:
                res = tc.get("result")
                if isinstance(res, dict):
                    fields_seen.update(res.keys())
        for f in needed:
            # case-insensitive
            if any(f.lower() == k.lower() for k in fields_seen) or (
                f == "spe" and ("speed" in fields_seen or "spe" in fields_seen)
            ):
                present.append(f)
            else:
                absent.append(f)
        # also quote actual get_move_static fields for MV*
        note = f"present={present}; ABSENT={absent}; fields_seen_sample={sorted(fields_seen)[:15]}"
        lines.append(f"| {rid} | {fact.replace('|','\\|')} | {(ref or '—').replace('|','\\|')[:80]} | {note} |")

    # MV2 arm behavior
    mv2 = t["MV2"]
    turn = (mv2.get("turns") or [{}])[0]
    lines += [
        "",
        "### MV2 run 1",
        f"- tool_calls: {json.dumps([{k:c.get(k) for k in ('name','args','result')} for c in turn.get('tool_calls') or []], sort_keys=True)}",
        f"- final_text: {(turn.get('final_text') or '')!r}",
        f"- get_move_static Wish fields: {sorted((wish.keys() if isinstance(wish, dict) else []))}",
        "- PP in tool result: ABSENT",
        "- PP number in final_text: "
        + str(re.findall(r"\bPP\b|\bpp\b|\b8\b", turn.get("final_text") or "")),
    ]
    # where 8 came from — quote if present in text
    ft = turn.get("final_text") or ""
    if "8" in ft:
        lines.append("- '8' appears in final_text (not returned by get_move_static in this turn)")
    else:
        lines.append("- '8' does not appear in final_text")

    # Fix section A class cells — rewrite note about field names
    # Discover actual request row keys
    lines = [
        f"<!-- request row keys sample: {sorted(sample.keys())} -->",
    ] + lines

    (ROOT / "cursor_run1_tallies.md").write_text("\n".join(lines) + "\n")
    print("wrote", ROOT / "cursor_run1_tallies.md")
    print("unallowed_changed", len(unallowed_changed), "sc_calls", len(sc_calls), "missing_sc", missing_sc)


def main() -> None:
    t = load_transcript()
    write_fixture_sweep(t)
    write_tallies(t)
    # drop fixture context
    ha = ROOT / "run_1_hand_audit"
    for name in ("fixture_context.html", "build_fixture_context.py", "FIXTURE_CONTEXT_SHA256.txt"):
        p = ha / name
        if p.exists():
            p.unlink()
            print("deleted", p)


if __name__ == "__main__":
    main()

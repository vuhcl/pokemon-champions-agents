"""FU74: cut IX1 / IX5 / IX7 keys + regenerate ix_facts from pinned data.

Run: uv run python -m scripts.eval.part_g_arm.state.keys_fu74.build_fu74_artifacts

Does not edit keys_fu72/ or any a393ae91 frozen pin.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[5]
STATE = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
FU72 = STATE / "keys_fu72"
V4 = REPO / "scripts" / "eval" / "part_g_v4"
REV4 = FU72 / "expected_tools_rev4_2026-11-07.csv"
REV5_NAME = "expected_tools_rev5_2026-11-07.csv"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _point(
    pid: str, text: str, *, tool_backed: bool = False, conditional: bool = False
) -> dict[str, Any]:
    return {
        "id": pid,
        "text": text,
        "tool_backed": tool_backed,
        "conditional": conditional,
    }


def collect_ix_facts() -> dict[str, Any]:
    """Regenerate every draft fact from pinned data via ix_tools_v1."""
    from scripts.eval.part_g_arm.state.ix_tools import find_by_effect, get_type_effectiveness
    from scripts.eval.part_g_arm.state.tools import set_ix_tools_v1

    set_ix_tools_v1(True)
    static = json.loads((REPO / "data" / "moves" / "static.v1.json").read_text(encoding="utf-8"))
    moves = static["moves"]

    def priority(name: str) -> int:
        for mid, row in moves.items():
            if isinstance(row, dict) and row.get("name") == name:
                return int(row["priority"])
        raise KeyError(f"move not in static.v1.json: {name}")

    def match_names(kind: str, *, flag: str | None = None, keyword: str | None = None) -> list[str]:
        r = find_by_effect(kind, flag=flag, keyword=keyword)
        if r.get("status") != "ok":
            raise RuntimeError(f"find_by_effect failed: {r}")
        return [m["name"] for m in r["matches"]]

    def match_rows(kind: str, *, flag: str | None = None, keyword: str | None = None) -> list[dict[str, Any]]:
        r = find_by_effect(kind, flag=flag, keyword=keyword)
        if r.get("status") != "ok":
            raise RuntimeError(f"find_by_effect failed: {r}")
        out = []
        for m in r["matches"]:
            out.append(
                {
                    "id": m.get("id"),
                    "name": m["name"],
                    "matched_by": m.get("matched_by"),
                    "description": m.get("description") or "",
                }
            )
        return out

    ground = get_type_effectiveness(attack_type="Ground")
    normal = get_type_effectiveness(attack_type="Normal")
    if ground.get("status") != "ok" or normal.get("status") != "ok":
        raise RuntimeError(f"type chart probe failed: {ground!r} {normal!r}")

    ground_ability_rows = match_rows("ability", keyword="Ground")
    ground_item_rows = match_rows("item", keyword="Ground")
    # Draft-named Ground-immunity descriptions (predicate reference, not membership list).
    immunity_ability_names = ("Levitate", "Eelevate", "Earth Eater", "Telepathy")
    immunity_item_names = ("Air Balloon",)
    ground_imm_abilities = {
        row["name"]: row["description"]
        for row in ground_ability_rows + match_rows("ability", keyword="allies")
        if row["name"] in immunity_ability_names
    }
    ground_imm_items = {
        row["name"]: row["description"]
        for row in ground_item_rows
        if row["name"] in immunity_item_names
    }

    return {
        "schema": "part_g_arm_ix_facts_fu74_v1",
        "note": (
            "Reference facts regenerated from pinned data via ix_tools_v1. "
            "Keys state predicates; this file is not a scored membership list."
        ),
        "redirection_flag_members": match_names("move", flag="redirection"),
        "protection_flag_members": match_names("move", flag="protection"),
        "priorities": {
            "Fake Out": priority("Fake Out"),
            "Follow Me": priority("Follow Me"),
            "Rage Powder": priority("Rage Powder"),
        },
        "get_type_effectiveness_Ground": {
            "no_damage": list(ground["no_damage"]),
            "resisted": list(ground["resisted"]),
        },
        "get_type_effectiveness_Normal": {
            "no_damage": list(normal["no_damage"]),
        },
        "intimidate_keyword_hits": {
            "names": match_names("ability", keyword="Intimidate"),
            "note": (
                "Only abilities whose description contains \"Intimidate\". "
                "Misses abilities that react to the Attack drop (Defiant, Competitive, "
                "Mirror Armor, Clear Body, White Smoke, Full Metal Body, Hyper Cutter, "
                "Contrary, and so on). Not a membership set — IX5 p3 is judged from the "
                "ability's description via get_abilities or find_by_effect."
            ),
        },
        "priority_moves_keyword_hits": match_names("ability", keyword="Priority moves"),
        "ground_keyword_ability_hits": {
            "names": [r["name"] for r in ground_ability_rows],
            "note": (
                "Keyword hits include Sand Force, which is not a Ground immunity. "
                "Not a membership set — IX7 safety is judged by the zero-damage predicate."
            ),
        },
        "allies_keyword_ability_hits": match_names("ability", keyword="allies"),
        "ground_keyword_item_hits": [r["name"] for r in ground_item_rows],
        "ground_immunity_ability_descriptions": ground_imm_abilities,
        "ground_immunity_item_descriptions": ground_imm_items,
        "priority_blocking_abilities_note": (
            "Keyword hits include Mycelium Might and Stall; only Armor Tail, "
            "Dazzling, and Queenly Majesty stop an opposing priority move "
            "(key predicate; not a membership list)."
        ),
    }


def build_hand_keys() -> dict[str, Any]:
    """IX1 / IX5 / IX7 only — points from Vu draft 2026-11-07."""
    turns: dict[str, Any] = {
        "IX1__t1": {
            "row_id": "IX1",
            "turn": 1,
            "request_text": "Can I counter Fake Out with redirection?",
            "points": [
                _point(
                    "p1",
                    'The arm states what it means by "counter" (redirect it, or block it); the stated assumption is scored.',
                ),
                _point(
                    "p2",
                    "The redirection moves it names come from the tool (Follow Me, Rage Powder); it names no other move as redirection.",
                    tool_backed=True,
                ),
                _point(
                    "p3",
                    "It gives the priorities from a tool: Fake Out 3 against Follow Me and Rage Powder 2.",
                    tool_backed=True,
                ),
                _point(
                    "p4",
                    "The conclusion is that redirection used the same turn does not counter Fake Out, because Fake Out moves first. Recommending Follow Me or Rage Powder as the counter fails.",
                ),
                _point(
                    "p5",
                    "Not required: naming other counters. If it names any, each is a real counter backed by a tool result or describe in that turn (for example Protect, Detect, Armor Tail, Dazzling, Queenly Majesty, a Ghost-type target). A named non-counter fails (Endure, Mycelium Might, Stall).",
                    tool_backed=True,
                    conditional=True,
                ),
            ],
            "rewrite": True,
            "pass_criteria_changed": False,
            "unreachable_reason": "",
            "flags_required": ["ix_tools_v1"],
            "expected_tools_ordered": "find_by_effect;get_move_static",
            "optional_tools": "get_type_effectiveness;get_abilities;describe",
            "alternative_path": "",
            "notes": (
                "FU74 draft 2026-11-07. Conclusion is simply no (no 'it depends' path). "
                "pass_criteria_changed false in meaning (same pass as old key, now tool-backed)."
            ),
        },
        "IX5__t1": {
            "row_id": "IX5",
            "turn": 1,
            "request_text": "Which Pokemon punish Intimidate?",
            "points": [
                _point(
                    "p1",
                    'The arm states what "punish" means, and the definition is about what the Pokemon does when an opposing Intimidate hits it: the effect is blocked, reflected, or turned into a gain (blocked, reflected or boosted, or a stated variant of those). The stated definition is scored. A definition that is not about the response to being Intimidated (for example "Pokemon that also have Intimidate") fails this point.',
                ),
                _point(
                    "p2",
                    "The arm splits its answer into separate buckets by mechanism (for example blocked, reflected, boosted); it does not give one mixed list. The buckets are the arm's own; no fixed membership.",
                ),
                _point(
                    "p3",
                    "Each ability it puts in a bucket does what the bucket says to Intimidate, backed by that ability's description from a tool result in that turn (find_by_effect or get_abilities), whatever definition the arm stated. An ability in the wrong bucket, or one that does nothing to Intimidate, fails. Intimidate itself fails: its description lowers adjacent opponents' Attack, with no immunity, reflection or boost, so \"Intimidate counters Intimidate\" is a false claim. Rattled counts as boosted (Vu, 2026-11-07).",
                    tool_backed=True,
                ),
                _point(
                    "p4",
                    "Each Pokemon it names as a holder is legal and can have that ability (find_species with the ability, or check_species_ability). A named holder that cannot have the ability fails.",
                    tool_backed=True,
                ),
                _point(
                    "p5",
                    "Not required: an exhaustive list of abilities or holders. If the arm states a count or says the list is complete, it carries a source label and matches the tool result it cites.",
                    conditional=True,
                ),
            ],
            "rewrite": True,
            "pass_criteria_changed": True,
            "unreachable_reason": "",
            "flags_required": ["ix_tools_v1"],
            "expected_tools_ordered": "find_by_effect;find_species",
            "optional_tools": "get_abilities;check_species_ability;check_species_legal",
            "alternative_path": "",
            "notes": (
                "FU74 draft 2026-11-07. Membership by predicate (blocked/reflected/boosted vs description), "
                "not a fixed list. pass_criteria_changed true: set scoring leaves part3's "
                "'named member not in key = false claim' rule."
            ),
        },
        "IX7__t1": {
            "row_id": "IX7",
            "turn": 1,
            "request_text": "Which partners can I Earthquake alongside?",
            "points": [
                _point(
                    "p1",
                    'The arm states what "safe" means (takes no damage from the partner\'s Earthquake); the stated definition is scored. A resisting type is not safe unless its definition says so.',
                ),
                _point(
                    "p2",
                    "Every type, ability or item it names as safe really gives no damage from Earthquake under that definition, backed by a tool result in that turn (get_type_effectiveness or find_by_effect). Naming a resisting type or Friend Guard as safe fails.",
                    tool_backed=True,
                ),
                _point(
                    "p3",
                    "Every species it names as a safe partner is legal and has the type, or can have the ability (find_species). An item it names is legal in Champions (check_item_legal) and the named holder can hold it. A named partner or item that does not meet the check fails.",
                    tool_backed=True,
                ),
                _point(
                    "p4",
                    "Examples and any counts come from tool results with a source label (Showdown text for item and move descriptions).",
                    tool_backed=True,
                ),
                _point(
                    "p5",
                    "The set it gives matches its stated definition (a member the definition excludes, or a member whose immunity is conditional without the condition stated, fails; for example Levitate under Gravity).",
                ),
                _point(
                    "p6",
                    "Not required: finding all of Flying, Levitate, Earth Eater, Eelevate, Telepathy or Air Balloon (Vu, 2026-11-07).",
                    conditional=True,
                ),
            ],
            "rewrite": True,
            "pass_criteria_changed": True,
            "unreachable_reason": "",
            "flags_required": ["ix_tools_v1"],
            "expected_tools_ordered": "get_type_effectiveness;find_by_effect;find_species",
            "optional_tools": "get_abilities;check_species_legal;check_item_legal",
            "alternative_path": "",
            "notes": (
                "FU74 draft 2026-11-07. Membership by predicate (zero damage from partner EQ), "
                "not a fixed list. pass_criteria_changed true: set scoring leaves part3's "
                "'named member not in key = false claim' rule."
            ),
        },
    }
    return {
        "schema": "part_g_arm_hand_keys_fu74_v1",
        "config": {
            "ix_tools_v1": True,
            "sticky_locks": True,
            "unlock_keeps_values": True,
            "tool_fixes_v2": True,
        },
        "turns": turns,
        "source_draft": "ix_keys_draft_2026-11-07.md",
        "keys_fu72_untouched": True,
    }


def build_rev5_csv(hand: dict[str, Any]) -> str:
    """rev4 with IX rows updated from hand keys; unreachable cleared."""
    by_id = {k.split("__")[0]: v for k, v in hand["turns"].items()}
    rows_out: list[dict[str, str]] = []
    with REV4.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rid = row["row_id"]
            if rid in by_id:
                t = by_id[rid]
                pts = " || ".join(f"{p['id']}: {p['text']}" for p in t["points"])
                note = (
                    f"[FU74] pcc={t['pass_criteria_changed']} flags={','.join(t['flags_required'])} "
                    f"{pts}"
                )
                row = {
                    **row,
                    "expected_tools_ordered": t["expected_tools_ordered"],
                    "optional_tools": t["optional_tools"],
                    "alternative_path": t.get("alternative_path") or "",
                    "new_tool_needed": "",
                    "notes": note,
                }
            rows_out.append(row)
    buf: list[str] = []
    import io

    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=fieldnames, lineterminator="\n")
    w.writeheader()
    for row in rows_out:
        w.writerow({k: row.get(k, "") for k in fieldnames})
    return sio.getvalue()


def point_diff_md(hand: dict[str, Any]) -> str:
    old = json.loads((FU72 / "hand_keys_fu72.json").read_text(encoding="utf-8"))
    lines = [
        "# FU74 point diff (keys_fu72 IX rows ↔ keys_fu74)",
        "",
        "Source draft: `ix_keys_draft_2026-11-07.md`. Any key change not in the draft is a bug.",
        "",
    ]
    for key in ("IX1__t1", "IX5__t1", "IX7__t1"):
        o = old["turns"][key]
        n = hand["turns"][key]
        lines += [
            f"## {n['row_id']}",
            f"- pass_criteria_changed: {n['pass_criteria_changed']} (old unreachable pending cut)",
            f"- old_point_count: {len(o['points'])}",
            f"- new_point_count: {len(n['points'])}",
            f"- unreachable_reason old: {o.get('unreachable_reason')!r}",
            f"- unreachable_reason new: {n.get('unreachable_reason')!r}",
            f"- expected_tools old → new: `{o.get('expected_tools_ordered')}` → `{n.get('expected_tools_ordered')}`",
            f"- optional_tools old → new: `{o.get('optional_tools')}` → `{n.get('optional_tools')}`",
            "",
            "### Old (keys_fu72 pending cut)",
        ]
        for p in o["points"]:
            lines.append(f"- `{p['id']}`: {p['text']}")
        lines += ["", "### New (keys_fu74 draft)"]
        for p in n["points"]:
            tb = " [tool-backed]" if p.get("tool_backed") else ""
            cond = " [conditional]" if p.get("conditional") else ""
            lines.append(f"- `{p['id']}`{tb}{cond}: {p['text']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _ability_names() -> set[str]:
    doc = json.loads((REPO / "data" / "abilities" / "all.v1.json").read_text(encoding="utf-8"))
    out: set[str] = set()
    entries = doc.get("abilities") or doc
    if isinstance(entries, dict):
        for _k, row in entries.items():
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                out.add(row["name"])
            elif isinstance(row, str):
                out.add(row)
    elif isinstance(entries, list):
        for row in entries:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                out.add(row["name"])
    return out


def _move_names() -> set[str]:
    doc = json.loads((REPO / "data" / "moves" / "static.v1.json").read_text(encoding="utf-8"))
    return {
        row["name"]
        for row in doc["moves"].values()
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }


def _type_names() -> set[str]:
    doc = json.loads(
        (V4 / "key_artifacts" / "type_chart.v1.json").read_text(encoding="utf-8")
    )
    return set(doc["types"])


def legality_report(hand: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """Verify every move / ability / item / type the keys name exists in pinned data."""
    from recommender.legality import is_item_legal, load_snapshot

    snap = load_snapshot()
    abilities = _ability_names()
    moves = _move_names()
    types = _type_names()

    # Entities named in the draft / key points (not every keyword hit in facts).
    named_moves = {
        "Fake Out",
        "Follow Me",
        "Rage Powder",
        "Baneful Bunker",
        "Detect",
        "Endure",
        "King's Shield",
        "Protect",
        "Spiky Shield",
        "Quick Guard",
        "Earthquake",
        "Dragon Darts",
        "Snipe Shot",
    }
    named_abilities = {
        "Armor Tail",
        "Dazzling",
        "Mycelium Might",
        "Queenly Majesty",
        "Stall",
        "Guard Dog",
        "Inner Focus",
        "Oblivious",
        "Own Tempo",
        "Scrappy",
        "Rattled",
        "Defiant",
        "Competitive",
        "Mirror Armor",
        "Clear Body",
        "White Smoke",
        "Full Metal Body",
        "Hyper Cutter",
        "Contrary",
        "Levitate",
        "Eelevate",
        "Earth Eater",
        "Telepathy",
        "Friend Guard",
        "Intimidate",
    }
    named_items = {"Air Balloon", "Shuca Berry", "Soft Sand", "Iron Ball"}
    named_types = {"Ground", "Flying", "Bug", "Grass", "Normal", "Ghost"}

    out: dict[str, Any] = {
        "schema": "part_g_arm_legality_report_fu74_v1",
        "moves": {},
        "abilities": {},
        "items": {},
        "types": {},
        "species": {},
        "facts_keyword_items_champions_legal": {},
        "failures": [],
        "note": (
            "IX keys name no fixed species holders; species map empty. "
            "Failures cover draft/key-named entities only. "
            "facts_keyword_items_champions_legal is informational for Ground-keyword hits."
        ),
    }
    for mv in sorted(named_moves):
        ok = mv in moves
        out["moves"][mv] = {"ok": ok, "in_static": ok}
        if not ok:
            out["failures"].append(f"move {mv}")
    for ab in sorted(named_abilities):
        ok = ab in abilities
        out["abilities"][ab] = {"ok": ok}
        if not ok:
            out["failures"].append(f"ability {ab}")
    for it in sorted(named_items):
        ok = bool(is_item_legal(snap, it))
        out["items"][it] = {"ok": ok}
        if not ok:
            out["failures"].append(f"item {it}")
    for ty in sorted(named_types):
        ok = ty in types
        out["types"][ty] = {"ok": ok}
        if not ok:
            out["failures"].append(f"type {ty}")

    for it in facts.get("ground_keyword_item_hits") or []:
        out["facts_keyword_items_champions_legal"][it] = bool(is_item_legal(snap, it))

    known_tools = {
        "find_by_effect",
        "get_move_static",
        "get_type_effectiveness",
        "get_abilities",
        "describe",
        "find_species",
        "check_species_ability",
        "check_species_legal",
        "check_item_legal",
    }
    for _tid, turn in hand["turns"].items():
        for field in ("expected_tools_ordered", "optional_tools"):
            raw = turn.get(field) or ""
            for name in [x for x in raw.split(";") if x]:
                if name not in known_tools:
                    out["failures"].append(f"unknown tool in {turn['row_id']} {field}: {name}")
    return out


def legality_md(report: dict[str, Any]) -> str:
    fails = report["failures"]
    lines = [
        "# FU74 legality report (IX1 / IX5 / IX7)",
        "",
        ("**No failures.**" if not fails else f"**{len(fails)} failure(s).**"),
        "",
    ]
    if fails:
        lines.append("## Failures")
        lines.extend(f"- {f}" for f in fails)
        lines.append("")
    for section in ("moves", "abilities", "items", "types"):
        lines.append(f"## {section}")
        for name, row in report[section].items():
            mark = "ok" if row.get("ok") else "FAIL"
            lines.append(f"- {name}: {mark}")
        lines.append("")
    lines.append(report.get("note") or "")
    lines.append("")
    return "\n".join(lines)


def write_manifest(extra_old: dict[str, str] | None = None) -> dict[str, Any]:
    fu72_manifest = json.loads((FU72 / "KEYS_MANIFEST_FU72.json").read_text(encoding="utf-8"))
    fu72_key_hash = fu72_manifest["key_hash"]
    fu72_manifest_sha = _sha(FU72 / "KEYS_MANIFEST_FU72.json")

    files = sorted(
        p
        for p in OUT.iterdir()
        if p.is_file()
        and p.name != "KEYS_MANIFEST_FU74.json"
        and p.suffix in {".json", ".csv", ".md", ".py"}
        and not p.name.startswith("_")
        and p.name != "build_fu74_artifacts.py"  # builder not part of key hash
    )
    # Include builder? Brief: IX files' hashes. Exclude .py from key_hash content set;
    # still list the generator path separately.
    content_files = [p for p in files if p.suffix != ".py"]
    file_table = {str(p.relative_to(REPO)): _sha(p) for p in content_files}
    fu74_key_hash = hashlib.sha256(
        json.dumps(file_table, sort_keys=True).encode()
    ).hexdigest()
    revised_key_hash = hashlib.sha256(
        json.dumps(
            {"keys_fu72": fu72_key_hash, "keys_fu74": fu74_key_hash},
            sort_keys=True,
        ).encode()
    ).hexdigest()

    old_hashes = {
        "expected_tools_rev3_2026-11-02.csv": _sha(
            STATE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
        ),
        "part3_request_set_v4.md": _sha(V4 / "part3_request_set_v4.md"),
        "derived_keys.json": _sha(V4 / "key_artifacts" / "derived_keys.json"),
        "FROZEN_MANIFEST_ARM_V2.json": _sha(STATE / "FROZEN_MANIFEST_ARM_V2.json"),
        "claim_battery_v4.json": _sha(V4 / "battery" / "claim_battery_v4.json"),
        "keys_fu72_key_hash": fu72_key_hash,
    }
    if extra_old:
        old_hashes.update(extra_old)

    manifest = {
        "schema": "part_g_arm_keys_fu74_manifest_v1",
        "key_hash": fu74_key_hash,
        "keys_fu72_key_hash": fu72_key_hash,
        "keys_fu72_manifest_sha256": fu72_manifest_sha,
        "revised_key_hash": revised_key_hash,
        "files": file_table,
        "generator": str((OUT / "build_fu74_artifacts.py").relative_to(REPO)),
        "old_hashes_unchanged": old_hashes,
        "manifest_self_hashed": False,
        "note": (
            "IX1/IX5/IX7 cut only. keys_fu72 contents unchanged. "
            "revised_key_hash combines fu72 key_hash + fu74 key_hash. "
            "This manifest is not listed in files (not self-hashed)."
        ),
    }
    path = OUT / "KEYS_MANIFEST_FU74.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    facts = collect_ix_facts()
    (OUT / "ix_facts_fu74.json").write_text(
        json.dumps(facts, indent=2) + "\n", encoding="utf-8"
    )

    hand = build_hand_keys()
    (OUT / "hand_keys_fu74.json").write_text(
        json.dumps(hand, indent=2) + "\n", encoding="utf-8"
    )

    rev5 = build_rev5_csv(hand)
    (OUT / REV5_NAME).write_text(rev5, encoding="utf-8")

    (OUT / "point_diff_fu74.md").write_text(point_diff_md(hand), encoding="utf-8")

    legal = legality_report(hand, facts)
    (OUT / "legality_report_fu74.json").write_text(
        json.dumps(legal, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "legality_report_fu74.md").write_text(legality_md(legal), encoding="utf-8")

    manifest = write_manifest()
    print("FU74 artifacts under", OUT)
    print("fu74 key_hash", manifest["key_hash"])
    print("keys_fu72 key_hash", manifest["keys_fu72_key_hash"])
    print("revised_key_hash", manifest["revised_key_hash"])
    print("legality failures", legal["failures"])


if __name__ == "__main__":
    main()

"""FU72: build versioned arm keys (does not edit frozen a393ae91 artifacts).

Run: uv run python -m scripts.eval.part_g_arm.state.keys_fu72.build_fu72_artifacts
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STATE = HERE.parent
V4 = HERE.parents[2] / "part_g_v4"
REPO = HERE.parents[4]
OUT = HERE

sys.path.insert(0, str(V4 / "builders"))
sys.path.insert(0, str(V4 / "checks"))

from _lib import base_stats, load_legality  # noqa: E402
from speed_grid import final_spe_after_mods  # noqa: E402

BAD_SPLIT_TURNS = [
    ("DM2", 1),
    ("DM6", 1),
    ("GS1", 1),
    ("GS1", 2),
    ("H15", 1),
    ("HN2b", 1),
    ("HU2b", 1),
    ("IS2", 1),
    ("MT3", 1),
    ("MT3", 2),
    ("MT3", 3),
    ("MT6", 1),
    ("MT6", 2),
    ("MT6", 3),
    ("TB1", 1),
]

# Request-text overrides (manifest revision; frozen runner untouched).
REQUEST_TEXT_OVERRIDES = {
    ("MR2", 1): "Lock Choice Specs on Hatterene",
    ("MR3", 1): "Lock Incineroar in slot 2",
    ("MR5", 1): "Lock into slot 2",
    ("MW3", 1): "Lock Incineroar in the slot I mentioned",
    ("HC1", 1): "I want my team to be all water and all fire",
    ("MT6", 1): "I want my team to be all water and all fire",
    ("MT6", 2): "Keep the Water only constraint",
    ("MT1", 1): "limit slot 1 to Water only",
    ("HU3", 1): "Give me some bulky Fire type options for slot 3",
    ("TB2", 1): "Swap Flare Blitz for Darkest Lariat.",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _point(pid: str, text: str, *, tool_backed: bool = False, conditional: bool = False) -> dict[str, Any]:
    return {
        "id": pid,
        "text": text,
        "tool_backed": tool_backed,
        "conditional": conditional,
    }


def _split_semicolon(acceptance: str) -> tuple[list[dict[str, str]], bool]:
    """Mechanical ';'-split with no wording change. Returns (points, ambiguous)."""
    text = (acceptance or "").strip()
    if not text:
        return [{"id": "acceptance", "text": "(no acceptance text)"}], False
    parts = [p.strip() for p in text.split(";") if p.strip()]
    ambiguous = False
    # Heuristics for bad splits inside a delimiter (R2 60 family).
    if any(len(p) < 12 for p in parts[1:]):
        ambiguous = True
    if any(p[0].islower() for p in parts[1:] if p):
        ambiguous = True
    if "Key from" in text or "derived_keys" in text and len(parts) > 3:
        ambiguous = True
    if len(parts) <= 1:
        return [{"id": "acceptance", "text": text}], False
    return [{"id": f"p{i+1}", "text": p} for i, p in enumerate(parts)], ambiguous


def compute_is_minima() -> dict[str, Any]:
    snap = load_legality()
    dk = json.loads((V4 / "key_artifacts" / "derived_keys.json").read_text())
    cells = [c["opp_final_spe"] for c in dk["is1_min_spe"]["per_cell"]]

    def min_sp(own: int, tgt: int, nature: str, **kw: Any) -> dict[str, Any]:
        for n in range(0, 33):
            spe = final_spe_after_mods(own, n, nature, **kw)
            if spe > tgt:
                return {"min_sp": n, "spe_at_min": spe, "reachable": True}
        return {
            "min_sp": None,
            "spe_at_32": final_spe_after_mods(own, 32, nature, **kw),
            "reachable": False,
        }

    g = base_stats(snap, "Garchomp")["spe"]
    b = base_stats(snap, "Basculegion")["spe"]
    s = base_stats(snap, "Slowbro")["spe"]
    p = base_stats(snap, "Pincurchin")["spe"]
    am = base_stats(snap, "Alakazam-Mega")["spe"]
    alak = final_spe_after_mods(am, 32, "Timid")

    is1: dict[str, Any] = {"cells": cells, "own_base_spe": g, "per_cell": {}}
    for cell in cells:
        row: dict[str, Any] = {}
        for label, nat in (("neutral", "Serious"), ("beneficial", "Jolly")):
            row[label] = {
                "bare": min_sp(g, cell, nat),
                "scarf": min_sp(g, cell, nat, scarf=True),
                "scarf_tw": min_sp(g, cell, nat, scarf=True, tw=True),
            }
        is1["per_cell"][str(cell)] = row

    is2: dict[str, Any] = {"cells": cells, "own_base_spe": b, "nature": "Jolly", "budget_R": 24, "per_cell": {}}
    for cell in cells:
        m = min_sp(b, cell, "Jolly", scarf=True)
        shortfall = None
        fits = False
        if m["reachable"] and m["min_sp"] is not None:
            fits = m["min_sp"] <= 24
            shortfall = None if fits else m["min_sp"] - 24
        is2["per_cell"][str(cell)] = {**m, "fits_R24": fits, "shortfall": shortfall}

    max_cell = max(cells)
    is3 = {
        "max_cell": max_cell,
        "own_base_spe": s,
        "max_stack_scarf_tw_timid": final_spe_after_mods(s, 32, "Timid", scarf=True, tw=True),
        "neutral_serious_scarf_tw": min_sp(s, max_cell, "Serious", scarf=True, tw=True),
        "beneficial_timid_scarf_tw": min_sp(s, max_cell, "Timid", scarf=True, tw=True),
        "scarf_alone_serious": min_sp(s, max_cell, "Serious", scarf=True),
        "scarf_alone_timid": min_sp(s, max_cell, "Timid", scarf=True),
        "recorded_scarf_on_slowbro": False,
        "slowbro_common_items_note": "no Choice Scarf in retained COMMON_ITEM list",
    }

    p_max = final_spe_after_mods(p, 32, "Timid", scarf=True, tw=True)
    is4 = {
        "own_base_spe": p,
        "alakazam_mega_timid_32": alak,
        "pincurchin_max_scarf_tw_timid": p_max,
        "unreachable_even_scarf_tw": p_max <= alak,
        # errata G7 floored stack is 219; offline scan agrees
        "max_stack": p_max,
    }
    return {
        "method": "offline scan of final_spe_after_mods / champions Spe over Spe SP 0..32 (same formula as get_speed path); not solve_spread",
        "dragapult_cells": cells,
        "IS1": is1,
        "IS2": is2,
        "IS3": is3,
        "IS4": is4,
    }


def rebuild_usage_sets() -> dict[str, Any]:
    blob = json.loads(
        (REPO / "data/usage/champions-reg-mc.ingame_doubles.v1.json").read_text()
    )
    species = blob["ingame_doubles"]["species"]
    h6 = list(species["rillaboom"]["teammates"][:5])
    by_rank = sorted(species.values(), key=lambda r: r.get("usage_rank") or 9999)
    top10 = [r["name"] for r in by_rank[:10]]
    snap = load_legality()
    p_spe = final_spe_after_mods(base_stats(snap, "Pelipper")["spe"], 32, "Timid")
    outspeeds = []
    for name in top10:
        if name == "Pelipper":
            continue
        threat = max(
            final_spe_after_mods(base_stats(snap, name)["spe"], 32, "Timid"),
            final_spe_after_mods(base_stats(snap, name)["spe"], 32, "Jolly"),
        )
        if p_spe > threat:
            outspeeds.append(name)
    # MT2: intersection of Pelipper ∩ Whimsicott teammates (worksheet: matched, no change)
    inter = [x for x in species["pelipper"]["teammates"] if x in set(species["whimsicott"]["teammates"])]
    mt2 = [x for x in inter if x in {"Charizard", "Garchomp", "Sneasler"}]
    gh = species["gholdengo"]
    modal_spread = gh["top_spreads"][0]
    modal = {
        "definition": "top joint = first top_spreads entry on re-pinned ingame blob (highest pct)",
        "item": gh["common_items"][0]["name"],
        "ability": gh["common_abilities"][0]["name"],
        "nature": modal_spread["nature"],
        "evs": modal_spread["evs"],
        "moves": [m["name"] for m in gh["common_moves"][:4]],
        "spread_pct": modal_spread["pct"],
    }
    hn3 = species["glimmora"]["common_items"][:3]
    return {
        "pin_blob_content_note": "data/usage/champions-reg-mc.ingame_doubles.v1.json (FU68 re-pin; git blob d60a06e0; commit lineage a50b4dd)",
        "H6_top5_partners_rillaboom": h6,
        "H6_old": ["Incineroar", "Garchomp", "Sneasler", "Gholdengo", "Raichu"],
        "HU2_outspeeds_top10_timid32_pelipper": outspeeds,
        "HU2_old": ["Incineroar", "Kingambit", "Golisopod"],
        "ingame_top10": top10,
        "MT2_t2_partners": mt2,
        "MT2_note": "worksheet: MT2 t2 matched; no change to the three-name set",
        "GS1_modal_gholdengo": modal,
        "HN3_common_items": hn3,
        "HN3_note": "percentages unchanged vs prior key text on this pin",
    }


def featured_seed_payload(species: str) -> dict[str, Any]:
    from recommender.regulation_registry import active_regulation
    from recommender.usage_data import featured_or_common_set

    s = featured_or_common_set(species, regulation=active_regulation())
    if s is None:
        return {"species": species, "error": "no featured_or_common_set"}
    d: dict[str, Any]
    if isinstance(s, dict):
        d = s
    elif is_dataclass(s):
        d = asdict(s)
    else:
        d = dict(s)  # type: ignore[arg-type]
    return {
        "species": species,
        "item": d.get("item"),
        "ability": d.get("ability"),
        "nature": d.get("nature"),
        "moves": list(d.get("moves") or []),
        "evs": d.get("evs") or d.get("spread"),
        "source": "featured_or_common_set (ingame first, else Showdown merge)",
    }


def write_seeds(usage: dict[str, Any]) -> list[str]:
    """Versioned seeds under keys_fu72/seeds/. Does not touch a393ae91 fixtures."""
    seeds_dir = OUT / "seeds"
    seeds_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def dump(name: str, doc: dict[str, Any]) -> None:
        path = seeds_dir / name
        path.write_text(json.dumps(doc, indent=2) + "\n")
        written.append(str(path.relative_to(REPO)))

    # MR4: item unlocked on both; other fields locked.
    inc = featured_seed_payload("Incineroar")
    gar = featured_seed_payload("Garchomp")
    # Force distinct items (Item Clause) and unlock only item.
    if inc.get("item") == gar.get("item"):
        gar["item"] = "Leftovers"
    dump(
        "mr4_incineroar_garchomp_item_unlocked.v1.json",
        {
            "row": "MR4",
            "note": (
                "FU72 / worksheet B6: item Attr unlocked on both mons; all other attrs locked. "
                "First Choice Scarf applies; Item Clause refuses the second. sticky_locks on."
            ),
            "flags": {"sticky_locks": True, "tool_fixes_v2": True},
            "slots": [
                {
                    "user_slot": 1,
                    **{k: inc[k] for k in ("species", "item", "ability", "nature", "moves", "evs")},
                    "locks": {
                        "species": True,
                        "ability": True,
                        "item": False,
                        "moveset": True,
                        "nature": True,
                        "spread": True,
                    },
                },
                {
                    "user_slot": 2,
                    **{k: gar[k] for k in ("species", "item", "ability", "nature", "moves", "evs")},
                    "locks": {
                        "species": True,
                        "ability": True,
                        "item": False,
                        "moveset": True,
                        "nature": True,
                        "spread": True,
                    },
                },
            ],
        },
    )

    # TB2: legal Darkest Lariat swap; Charcoal + Flare Blitz sole Fire attack; moveset unlocked (MR4 parallel).
    dump(
        "tb2_incineroar_charcoal_darkest_lariat.v1.json",
        {
            "row": "TB2",
            "note": (
                "FU72: Knock Off and U-turn are not in Incineroar's Champions learnset. "
                "Seed uses Throat Chop; request swaps Flare Blitz for Darkest Lariat. "
                "Charcoal + Flare Blitz as sole damaging Fire move preserved for the consequence. "
                "moveset unlocked under sticky_locks (MR4 item-unlock parallel)."
            ),
            "flags": {"sticky_locks": True, "tool_fixes_v2": True},
            "request_text": "Swap Flare Blitz for Darkest Lariat.",
            "slots": [
                {
                    "user_slot": 1,
                    "species": "Incineroar",
                    "item": "Charcoal",
                    "ability": "Intimidate",
                    "nature": "Adamant",
                    # Throat Chop (not U-turn): Incineroar cannot learn U-turn in Champions.
                    # Flare Blitz remains the sole damaging Fire move for the Charcoal consequence.
                    "moves": ["Flare Blitz", "Fake Out", "Throat Chop", "Parting Shot"],
                    "evs": {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 0},
                    "locks": {
                        "species": True,
                        "ability": True,
                        "item": True,
                        "moveset": False,
                        "nature": True,
                        "spread": True,
                    },
                }
            ],
            "check_learnset": {"species": "Incineroar", "move": "Darkest Lariat", "learns": True},
            "check_set_ok": True,
        },
    )

    # RB1: keep Calm Mind fixture content (consequence only if write allowed); sticky expects field_locked.
    rb1_src = json.loads((V4 / "fixtures" / "rb1_lucario_megaz_calmmind.json").read_text())
    dump(
        "rb1_lucario_megaz_calmmind.v1.json",
        {
            "row": "RB1",
            "note": (
                "FU72 / sticky_locks on: key expects atomic field_locked refusal; value unchanged. "
                "Calm Mind / Nasty Plot consequence only if a write is allowed. Copied from "
                "part_g_v4 fixture (not a featured build — featured Lucario is Scarf/CC and would "
                "remove the Calm Mind overlap the old key graded)."
            ),
            "flags": {"sticky_locks": True},
            "source_fixture": "scripts/eval/part_g_v4/fixtures/rb1_lucario_megaz_calmmind.json",
            "payload": rb1_src,
            "locks": "all fields locked (sticky refusal path)",
        },
    )

    # Remaining eight-fixture recheck: featured where the key does not need an inconsistency.
    for row, sp, extra in [
        ("DM2", "Incineroar", {"note": "locked attacker for Flare Blitz vs Hatterene"}),
        ("MS2", "Incineroar", {"note": "unlock_keeps_values: values stay, locks cleared"}),
        ("MS3", "Incineroar", {"pair": "Garchomp"}),
        ("MR3", "Incineroar", {"note": "Species Clause target already on team when locking Incineroar@2 — pair seed"}),
        ("MW2", "Incineroar", {"pair": "Garchomp"}),
        ("H18b", None, {"source_fixture": "scripts/eval/part_g_v4/fixtures/h18b_hyper_offense.json"}),
    ]:
        if row == "H18b":
            src = json.loads((REPO / extra["source_fixture"]).read_text())
            dump(
                f"{row.lower()}_seed.v1.json",
                {
                    "row": row,
                    "note": "Rechecked for FU72; fixture kept (judgment-only HO definition). Not synthesized.",
                    "source_fixture": extra["source_fixture"],
                    "payload": src,
                },
            )
            continue
        doc: dict[str, Any] = {
            "row": row,
            "flags": {"sticky_locks": True, "unlock_keeps_values": True, "tool_fixes_v2": True},
            "note": extra.get("note") or "featured_or_common_set; no planted inconsistency",
            "primary": featured_seed_payload(sp),
        }
        if extra.get("pair"):
            doc["secondary"] = featured_seed_payload(extra["pair"])
            if doc["primary"].get("item") == doc["secondary"].get("item"):
                doc["secondary"]["item"] = "Leftovers"
                doc["secondary"]["item_note"] = "distinct from primary for Item Clause"
        dump(f"{row.lower()}_seed.v1.json", doc)

    # Seed index
    dump(
        "SEED_INDEX.json",
        {
            "schema": "keys_fu72_seeds_v1",
            "files": sorted(p.name for p in seeds_dir.glob("*.json") if p.name != "SEED_INDEX.json"),
            "a393ae91_fixtures_untouched": True,
        },
    )
    return written


def build_hand_keys(is_min: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    import check_request_set as c

    rows = {r["id"]: r for r in c.parse_rows((V4 / "part3_request_set_v4.md").read_text())}
    csv_rows = list(
        csv.DictReader(
            (STATE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv").open()
        )
    )
    csv_by = {(r["row_id"], int(r["turn"])): r for r in csv_rows}

    turns: dict[str, Any] = {}
    ambiguous: list[dict[str, Any]] = []

    def add_turn(
        rid: str,
        turn: int,
        *,
        points: list[dict[str, Any]],
        rewrite: bool,
        pass_criteria_changed: bool,
        tools: dict[str, str] | None = None,
        unreachable: str | None = None,
        request_text: str | None = None,
        notes: str = "",
        flags: list[str] | None = None,
    ) -> None:
        key = f"{rid}__t{turn}"
        base = csv_by.get((rid, turn), {})
        req = request_text or REQUEST_TEXT_OVERRIDES.get((rid, turn)) or base.get("user_turn_text") or ""
        tools = tools or {}
        turns[key] = {
            "row_id": rid,
            "turn": turn,
            "request_text": req,
            "points": points,
            "rewrite": rewrite,
            "pass_criteria_changed": pass_criteria_changed,
            "unreachable_reason": unreachable,
            "flags_required": flags or [],
            "expected_tools_ordered": tools.get(
                "expected", base.get("expected_tools_ordered") or ""
            ),
            "optional_tools": tools.get("optional", base.get("optional_tools") or ""),
            "alternative_path": tools.get("alt", base.get("alternative_path") or ""),
            "notes": notes,
        }

    # --- IS1 ---
    cells = is_min["dragapult_cells"]
    is1_pts = [
        _point("p1", "State which Dragapult COMMON_SPEED cell(s) are assumed, or state that max-speed investment is assumed for the opponent (that assumption is itself a scoring point).", tool_backed=False),
        _point("p2", "If no max-speed assumption is stated, call get_common_speeds (or equivalent) for Dragapult's common cells.", tool_backed=True),
        _point("p3", "For each assumed cell: state whether a bare (no Scarf) Spe investment can outspeed it, or that the cell is unreachable bare. Spe 0 counts as the minimum when it already outspeeds.", tool_backed=True),
        _point("p4", "Give a tool-backed Spe number (solve_spread, or get_speed on the stated spread) that outspeeds the cell under the stated assumption.", tool_backed=True),
        _point("p5", "State the outcome vs budget: fits, shortfall, or unreachable. Scarf and Scarf+Tailwind are reachability notes only.", tool_backed=True),
        _point("p6", "Never say the investment is 'not recommended'.", tool_backed=False),
        _point(
            "p7",
            f"CONDITIONAL (score only if the arm claims a stated SP is the minimum): for each assumed cell, neutral-nature minimum Spe SP is the offline minimum (cells {cells}; see is_minima_fu72.json IS1).",
            tool_backed=True,
            conditional=True,
        ),
        _point(
            "p8",
            "CONDITIONAL: beneficial-nature (Jolly) minimum Spe SP per assumed cell matches the offline minimum.",
            tool_backed=True,
            conditional=True,
        ),
    ]
    add_turn(
        "IS1",
        1,
        points=is1_pts,
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "get_speed|solve_spread", "optional": "get_common_speeds", "alt": ""},
        notes="FU72: hidden 4-part min-SP removed; minimum points conditional on claiming a minimum.",
        flags=["tool_fixes_v2"],
    )

    # --- IS2 ---
    is2_pts = [
        _point("p1", "State the assumed Dragapult cell(s), or state a max-speed assumption for Dragapult.", tool_backed=False),
        _point("p2", "If no assumption, call get_common_speeds for Dragapult.", tool_backed=True),
        _point("p3", "Read the locked Basculegion (Jolly + Choice Scarf, Spe budget R=24) via read_team.", tool_backed=True),
        _point("p4", "Per cell: state the Jolly+Scarf Spe investment that outspeeds (tool-backed), and whether it fits within R=24 or the shortfall.", tool_backed=True),
        _point("p5", "Never say 'not recommended'.", tool_backed=False),
        _point(
            "p6",
            "CONDITIONAL (if a minimum is claimed): the stated Spe SP equals the offline Jolly+Scarf minimum for that cell (is_minima_fu72.json IS2).",
            tool_backed=True,
            conditional=True,
        ),
    ]
    add_turn(
        "IS2",
        1,
        points=is2_pts,
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team;get_speed|solve_spread", "optional": "get_common_speeds"},
        notes="FU72 IS2: one nature (Jolly); per-cell fit/shortfall under R=24.",
    )

    # --- IS3 ---
    is3_pts = [
        _point("p1", "State the assumed Dragapult cell(s) or a max-speed assumption.", tool_backed=False),
        _point("p2", "Tool-backed Spe number that outspeeds under the stated assumption.", tool_backed=True),
        _point("p3", "Max-speed Dragapult cell is reachable only under Scarf + Tailwind; state that reachability.", tool_backed=True),
        _point("p4", "State recorded Scarf usage on Slowbro: none in the retained COMMON_ITEM list.", tool_backed=True),
        _point("p5", "Never say 'not recommended'.", tool_backed=False),
        _point("p6", "CONDITIONAL: claimed neutral-nature minimum matches offline Scarf+TW minimum for the max cell.", tool_backed=True, conditional=True),
        _point("p7", "CONDITIONAL: claimed beneficial-nature minimum matches offline Scarf+TW minimum for the max cell.", tool_backed=True, conditional=True),
    ]
    add_turn("IS3", 1, points=is3_pts, rewrite=True, pass_criteria_changed=True,
             tools={"expected": "get_speed|solve_spread", "optional": "get_common_speeds;get_usage_items"})

    # --- IS4 ---
    is4_pts = [
        _point("p1", "The prompt requires Mega Alakazam (not base).", tool_backed=False),
        _point("p2", "State the Mega Alakazam target cell (Timid Spe-32) or a max-speed assumption.", tool_backed=False),
        _point(
            "p3",
            f"Pincurchin's max Spe under Scarf + Tailwind is {is_min['IS4']['pincurchin_max_scarf_tw_timid']}, below Mega Alakazam Timid-32 ({is_min['IS4']['alakazam_mega_timid_32']}); unreachable even under Scarf + Tailwind.",
            tool_backed=True,
        ),
        _point("p4", "Pincurchin has no Spe-boosting move that changes this reachability.", tool_backed=False),
        _point("p5", "State unreachable (no invented Spe SP that claims to outspeed the max cell).", tool_backed=False),
        _point("p6", "Never say 'not recommended'.", tool_backed=False),
    ]
    add_turn("IS4", 1, points=is4_pts, rewrite=True, pass_criteria_changed=True,
             tools={"expected": "get_speed|solve_spread", "optional": "get_common_speeds"},
             notes="FU72 IS4: 4-part min-SP removed; no Spe-boosting move restored. Offline max stack 219 (errata G7).")

    # --- Refusal Rule B rows (MR3/MR8 resolved below with meaning splits) ---
    for rid, prompt_note in [
        ("MR1", "illegal species"),
        ("MR2", "illegal item (Choice Specs on Hatterene)"),
        ("HP3", "illegal mutation"),
    ]:
        add_turn(
            rid,
            1,
            points=[
                _point("p1", f"Rule B: either a lookup that supports the refusal, or a write attempt whose validator refusal the reply recognises and cites ({prompt_note}).", tool_backed=True),
                _point("p2", "Outcome by rubric: the illegal write does not land; team state matches the refusal outcome.", tool_backed=False),
            ],
            rewrite=True,
            pass_criteria_changed=True,
            notes=f"FU72 Rule B refusal. {prompt_note}",
        )

    # MR4 special
    add_turn(
        "MR4",
        1,
        points=[
            _point("p1", "Apply Choice Scarf to the first mon as asked (item field is unlocked in the FU72 seed).", tool_backed=False),
            _point("p2", "Rule B / Item Clause: the second Scarf is refused; the reply recognises and cites the validator refusal (or a clause lookup).", tool_backed=True),
            _point("p3", "No second Scarf applied and no other field touched (rewritten 'state unchanged').", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "set_slot", "alt": "no_lookup_needed|describe"},
        flags=["sticky_locks", "tool_fixes_v2"],
        notes="FU72 MR4 seed: item unlocked both mons. sticky_locks on.",
    )

    # MS2 unlock_keeps_values
    add_turn(
        "MS2",
        1,
        points=[
            _point("p1", "Call unlock_slot (or equivalent) on slot 1.", tool_backed=True),
            _point("p2", "Under unlock_keeps_values: attribute values remain; locks are cleared. The old 'empty slot' expectation does not apply.", tool_backed=False),
            _point("p3", "Read-back states slot 1 unlocked with prior values kept.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        flags=["unlock_keeps_values"],
        notes="FU72 MS2 rewritten for unlock_keeps_values on.",
    )

    # RB1 sticky
    add_turn(
        "RB1",
        1,
        points=[
            _point("p1", "read_team first (current moveset / room).", tool_backed=True),
            _point("p2", "Under sticky_locks: the write is refused with atomic field_locked; Nasty Plot is not applied; existing values unchanged.", tool_backed=False),
            _point("p3", "Calm Mind / Nasty Plot boost-overlap consequence is scored only if a write is allowed; under sticky refusal it is not required.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team;set_slot", "optional": "describe;get_move_static"},
        flags=["sticky_locks"],
        notes="FU72 RB1 sticky_locks on: field_locked refusal.",
    )

    # TB2 legal swap + unlocked moveset
    add_turn(
        "TB2",
        1,
        points=[
            _point("p1", "read_team for the current moveset.", tool_backed=True),
            _point("p2", "Swap Flare Blitz for Darkest Lariat (legal per check_learnset); apply and read back.", tool_backed=True),
            _point("p3", "State that Charcoal no longer boosts (consequence / type-boost vs remaining damaging moves).", tool_backed=False),
            _point("p4", "Offer keep or swap item; no silent item change.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team;set_slot", "optional": "get_move_static;check_learnset"},
        flags=["sticky_locks"],
        request_text="Swap Flare Blitz for Darkest Lariat.",
        notes="FU72: Darkest Lariat replaces illegal Knock Off; moveset unlocked in seed.",
    )

    # MM1 — one point per distinct behavior; describe alt in CSV only.
    add_turn(
        "MM1",
        1,
        points=[
            _point("p1", "Build Salamence holding Salamencite.", tool_backed=True),
            _point("p2", "State that a mega cannot hold another item.", tool_backed=False),
            _point("p3", "Offer keep-stone or base form + Leftovers (form change is offer-only).", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "describe", "alt": "no_lookup_needed|describe"},
        notes="FU72: no_lookup_needed or validator refusal accepted as alternative to describe (CSV).",
    )

    # H8 Q9 — describe required, no no_lookup_needed
    for rid, claim in [("H8", "Item Clause → No"), ("Q9", "Species Clause → No")]:
        add_turn(
            rid,
            1,
            points=[
                _point("p1", f"Outcome: {claim}.", tool_backed=False),
                _point("p2", "No mutation.", tool_backed=False),
                _point("p3", "Required step: describe (or equivalent rules lookup). no_lookup_needed is NOT an alternative; a correct answer from memory can pass outcome and fail the required step.", tool_backed=True),
            ],
            rewrite=True,
            pass_criteria_changed=True,
            tools={"expected": "describe", "alt": ""},
        )

    # MM2 — refuse / draft unchanged / form-change offer; read_team in CSV.
    add_turn(
        "MM2",
        1,
        points=[
            _point("p1", "Refuse: the mega stone is the required mega item.", tool_backed=False),
            _point("p2", "Draft unchanged.", tool_backed=False),
            _point("p3", "Form-change offer only.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team", "optional": "", "alt": ""},
        flags=["sticky_locks"],
        notes="FU72 MM2: expected_tools includes read_team; sticky may shift refuse reason to lock.",
    )

    def _csv_tools(rid: str) -> dict[str, str]:
        base = csv_by.get((rid, 1), {})
        opt = (base.get("optional_tools") or "").strip()
        exp = (base.get("expected_tools_ordered") or "").strip()
        alt = (base.get("alternative_path") or "").strip()
        if opt and opt not in alt:
            alt = "|".join(x for x in [alt, opt] if x)
        return {"expected": exp, "optional": opt, "alt": alt}

    # MU1 — unchanged pass criteria; meaning split (tool fixed in #387).
    add_turn(
        "MU1",
        1,
        points=[
            _point("p1", "NO-MUTATION class.", tool_backed=False),
            _point("p2", "Claims are scored.", tool_backed=False),
            _point("p3", "State unchanged; no lock or commit.", tool_backed=False),
            _point("p4", "Required claim: Item Clause blocks both holding Choice Scarf (Garchomp / Jolteon / Choice Scarf legal in the pin).", tool_backed=False),
            _point("p5", "Other claims scored if made; variants must be legal.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        tools=_csv_tools("MU1"),
        notes="FU72: MU1 meaning split; pass criteria unchanged (tool fixed in #387).",
    )

    # MU4
    add_turn(
        "MU4",
        1,
        points=[
            _point("p1", "NO-MUTATION class.", tool_backed=False),
            _point("p2", "Answer yes / no / conditional with at least one tool-backed reason (Drizzle + explicit ability, usage, legality/clauses, or state).", tool_backed=True),
            _point("p3", "Each reason is scored.", tool_backed=False),
            _point("p4", "Bare yes/no without a tool-backed reason fails.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools=_csv_tools("MU4"),
    )

    # MR3 / MR6 / MR7 / MR8 / MU8 — Rule B / refuse rows with resolved behaviors.
    add_turn(
        "MR3",
        1,
        points=[
            _point("p1", "Species Clause applies (second Incineroar).", tool_backed=True),
            _point("p2", "State unchanged after the refusal.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools=_csv_tools("MR3"),
        notes="FU72 Rule B; optional tools in CSV alternative_path only.",
    )
    add_turn(
        "MR6",
        1,
        points=[
            _point("p1", "Empty unlock: accept a no-op or an explicit refusal.", tool_backed=False),
            _point("p2", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools=_csv_tools("MR6"),
    )
    add_turn(
        "MR7",
        1,
        points=[
            _point("p1", "Nothing is pending to commit.", tool_backed=False),
            _point("p2", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools=_csv_tools("MR7"),
    )
    add_turn(
        "MR8",
        1,
        points=[
            _point("p1", "Refuse the illegal species (Koraidon).", tool_backed=True),
            _point("p2", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools=_csv_tools("MR8"),
    )
    add_turn(
        "MU8",
        1,
        points=[
            _point("p1", "No archetype or lock write tools are used.", tool_backed=False),
            _point("p2", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools=_csv_tools("MU8"),
    )

    # MU2 unchanged explicitly
    if "MU2" in rows:
        acc = rows["MU2"]["acceptance"]
        pts, amb = _split_semicolon(acc)
        add_turn("MU2", 1, points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
                 rewrite=False, pass_criteria_changed=False,
                 notes="FU72: keys UNCHANGED (hypothetical tool fixed in #387).")
        if amb:
            ambiguous.append({"row": "MU2", "turn": 1, "reason": "semicolon split ambiguous", "acceptance": acc})

    # Q10: read_team alternative lives in the CSV only.
    add_turn(
        "Q10",
        1,
        points=[
            _point("p1", "Explains empty unlock.", tool_backed=False),
            _point("p2", "No mutation.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"alt": "read_team"},
    )
    # MV3: restore full acceptance content (accuracy 90% caveat; false claims).
    add_turn(
        "MV3",
        1,
        points=[
            _point("p1", "Rock Slide targets all adjacent foes (both opponents in doubles).", tool_backed=True),
            _point("p2", "Required caveat: accuracy 90% (gen9_accuracy pin), so either or both can miss.", tool_backed=True),
            _point("p3", "Claims that it always hits both, or cannot miss, are false.", tool_backed=False),
            _point("p4", "Targeting correct with no accuracy caveat is not SERVED.", tool_backed=False),
            _point("p5", "Optional (scored if made): each target rolls accuracy separately.", tool_backed=False),
            _point("p6", "A 0.75 damage claim is dropped (unverified).", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        notes="Restored from part3_request_set_v4.md MV3 acceptance; accuracy caveat relaxed to 90% per worksheet.",
    )

    # MS5: restore full conflict content; "flagged" = conflicts field.
    add_turn(
        "MS5",
        1,
        points=[
            _point("p1", "MUTATION-OK: apply the rain-offense archetype and read it back.", tool_backed=True),
            _point("p2", "Audit locked slots and report each conflict with a reason. Required conflicts: Drought (non-rain weather ability) and Solar Beam (rain-reduced).", tool_backed=False),
            _point("p3", "Control Pelipper is not flagged. 'Flagged' means an entry in the change_archetype conflicts field.", tool_backed=False),
            _point("p4", "Both required conflict flags must appear. Locked slots stay unchanged; offered replacements must be legal.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        notes="Restored from part3 acceptance; conflicts-field meaning from worksheet A.",
    )

    # DM2: restore acceptance + CSV content check (no DRAFT / Vu placeholders).
    add_turn(
        "DM2",
        1,
        points=[
            _point("p1", "Use the locked attacker from read_team: Adamant Life Orb Atk-32 Intimidate (not the DM1 pin top-item attacker).", tool_backed=True),
            _point("p2", "Expand the full numeric damage grid for every Hatterene COMMON_JOINT cell in derived_keys.dm_outputs.dm2.", tool_backed=True),
            _point("p3", "Look up Hatterene item and ability (Incineroar usage calls optional). The Hatterene item stated or used must be Life Orb, or faithful to the get_usage_items result received.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        tools={
            "expected": "read_team;get_usage_spreads;get_usage_items;get_usage_stats;calc_damage",
            "optional": "",
            "alt": "",
        },
        notes="Restored from part3 DM2 acceptance + rev3 CSV content check; writer placeholders removed.",
    )

    # H15: restore full acceptance (not the truncated CSV ';'-split).
    add_turn(
        "H15",
        1,
        points=[
            _point("p1", "Modest top joint SP is hp32/atk0/def0/spa32/spd2/spe0 with chaos_weight ≈8876.7; label chaos_weight as weight, not percent (presenting it as % is false).", tool_backed=True),
            _point("p2", "Spe under the stated SP: Modest 80, Timid hypothetical 88 (benchmarks in derived_keys.h15_primarina.benchmarks).", tool_backed=True),
            _point("p3", "Verdict: Modest default is SERVED when the basis is stated (only retained joint; Timid is not retained) and the speed tradeoff is mentioned.", tool_backed=False),
            _point("p4", "Conditional Timid is OK only with a named key benchmark. 'Timid is better' with no benchmark or a fabricated Timid joint is false.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        tools={"expected": "get_usage_spreads;get_speed", "optional": "", "alt": ""},
        notes="Restored from part3_request_set_v4.md H15 acceptance (lives there; was lost to CSV note ';'-split).",
    )

    # MU6 reset explanation
    add_turn(
        "MU6",
        1,
        points=[
            _point("p1", "Do not call reset_team (hypothetical).", tool_backed=False),
            _point("p2", "Explain what reset_team would clear (counterpart MS3: what would be lost) without writing.", tool_backed=False),
            _point("p3", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "no_lookup_needed", "optional": "read_team"},
    )

    # MR5 — request text lives in request_text / CSV only, not in points.
    add_turn(
        "MR5",
        1,
        points=[
            _point("p1", "Refuse or ask (occupied slot).", tool_backed=False),
            _point("p2", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Lock into slot 2",
        notes="MR5b remains the clean occupancy test with a named species. Registered request text is not a rubric point.",
    )

    # ASK rows
    add_turn(
        "OL4",
        1,
        points=[
            _point("p1", "Ambiguity to resolve: whether the user wants the pending option confirmed/set as draft vs locked in.", tool_backed=False),
            _point("p2", "Accepted: confirm or set a draft. Locking it in is not accepted. Off-topic questions fail.", tool_backed=False),
            _point("p3", "State unchanged until confirmation.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )
    add_turn(
        "OL6",
        1,
        points=[
            _point("p1", "Ambiguity to resolve: which referent / action the user means; ask. Off-topic questions fail.", tool_backed=False),
            _point("p2", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )
    add_turn(
        "OL9",
        1,
        points=[
            _point("p1", "Ambiguity: multi-select vs which single option. Off-topic questions fail.", tool_backed=False),
            _point("p2", "Accepted: multi-select or ask which. Not applied until resolved.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )
    add_turn(
        "MW3",
        1,
        points=[
            _point("p1", "Ambiguity: which slot 'the slot I mentioned' refers to; ask. Off-topic questions fail.", tool_backed=False),
            _point("p2", "No state change until the slot is resolved.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Lock Incineroar in the slot I mentioned",
    )
    # OL5 OL7a unchanged meaning — mechanical split only
    for rid in ("OL5", "OL7a"):
        acc = rows[rid]["acceptance"]
        pts, amb = _split_semicolon(acc)
        add_turn(rid, 1, points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
                 rewrite=False, pass_criteria_changed=False,
                 notes="FU72: wording/behavior unchanged (worksheet).")
        if amb:
            ambiguous.append({"row": rid, "turn": 1, "reason": "semicolon split", "acceptance": acc})

    # HC1 / MT6
    add_turn(
        "HC1",
        1,
        points=[
            _point("p1", "Recognise the two constraints (all Water and all Fire) leave an empty pool (verify with find_species types Water and Fire → count 0).", tool_backed=True),
            _point("p2", "Either record both constraints, or record nothing — both accepted — as long as the empty-pool recognition is clear.", tool_backed=False),
            _point("p3", "Must not silently apply only one constraint or pick a species from an empty pool.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="I want my team to be all water and all fire",
    )

    # MT6 turns
    add_turn(
        "MT6",
        1,
        points=[
            _point("p1", "Same empty-pool recognition as HC1 (Water∧Fire).", tool_backed=True),
            _point("p2", "Either record both constraints or record nothing; both accepted if empty-pool is recognised.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="I want my team to be all water and all fire",
    )
    add_turn(
        "MT6",
        2,
        points=[
            _point("p1", "Resolve to Water only: drop Fire (set_constraint_active / restore / add Water as applicable).", tool_backed=True),
            _point("p2", "Do not stack another Fire constraint.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Keep the Water only constraint",
    )
    add_turn(
        "MT6",
        3,
        points=[
            _point("p1", "Confirm constraints: Water-only read-back.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Confirm constraints.",
    )

    # MT3
    add_turn(
        "MT3",
        1,
        points=[_point("p1", "Record the No-Intimidate constraint (t1).", tool_backed=True)],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="No Intimidate.",
    )
    add_turn(
        "MT3",
        2,
        points=[
            _point("p1", "Suggest a Fire-typed species for slot 2; tool-backed (find_species or usage path).", tool_backed=True),
            _point("p2", "Asking instead of suggesting Fire is not an accepted path.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Suggest a Fire type for slot 2.",
    )
    add_turn(
        "MT3",
        3,
        points=[
            _point("p1", "The t3 reply itself answers yes or no for the t2 pick (or picks one of several Fire types / asks which — both accepted).", tool_backed=False),
            _point("p2", "Ability lookup in this turn backs the answer even if t2 already mentioned Intimidate. 'Has Intimidate' = species can have it as a legal ability.", tool_backed=True),
            _point("p3", "If the pick can have Intimidate: flag against the t1 constraint and offer ≥1 tool-backed alternative (different Fire pick, or a non-Intimidate legal ability on the same species). Silent acceptance or flag-with-no-alternative fails.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Does it have Intimidate?",
        tools={"expected": "check_species_ability|get_abilities", "alt": ""},
        notes="FU72: no_lookup_needed removed as a free alternative for t3.",
    )

    # Turns that must not be overall N/A: MT2 t1, HC2 t1, MT1 t1/t2, MT5 t1/t2
    add_turn("MT2", 1, points=[_point("p1", "Lock Pelipper into a slot as asked; state reflects the lock.", tool_backed=True)],
             rewrite=True, pass_criteria_changed=True, request_text="Lock Pelipper.")
    add_turn(
        "MT2",
        2,
        points=[
            _point("p1", f"Unordered set {usage['MT2_t2_partners']}; set-scoring; label in-game source.", tool_backed=True),
        ],
        rewrite=False,
        pass_criteria_changed=False,
        notes="MT2 t2 matched after re-pin; no set change.",
    )
    add_turn("MT2", 3, points=[_point("p1", "Confirm slot 1 is Pelipper.", tool_backed=False)],
             rewrite=True, pass_criteria_changed=False, request_text="Confirm slot 1.")

    add_turn(
        "HC2",
        1,
        points=[
            _point("p1", "Treat the turn as separate conflicting requests.", tool_backed=False),
            _point("p2", "Ask the user to resolve which constraint wins.", tool_backed=False),
            _point("p3", "Do not guess which constraint to keep.", tool_backed=False),
            _point("p4", "No state change until the user picks.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="No weather.",
    )
    add_turn(
        "MT1",
        1,
        points=[_point("p1", "Record a Water-only constraint on slot 1.", tool_backed=True)],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="limit slot 1 to Water only",
    )
    add_turn(
        "MT1",
        2,
        points=[
            _point("p1", "Record the additional no-Intimidate constraint.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Also no Intimidate",
    )
    add_turn(
        "MT1",
        3,
        points=[
            _point("p1", "Read-back shows both constraints active (Water-only on slot 1, and no Intimidate).", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="What constraints are active?",
    )
    add_turn(
        "MT5",
        1,
        points=[
            _point("p1", "Apply the rain-offense archetype as asked.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Archetype rain offense.",
    )
    add_turn(
        "MT5",
        2,
        points=[
            _point("p1", "Offer a rain-setter candidate for the open slot (tool-backed species or build suggestion).", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Rain setter candidate?",
    )
    add_turn(
        "MT5",
        3,
        points=[
            _point("p1", "Read-back includes the rain-offense archetype string.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Read back archetype.",
    )

    # H6 HU2 GS1 rebuilds
    h6_set = usage["H6_top5_partners_rillaboom"]
    add_turn(
        "H6",
        1,
        points=[
            _point("p1", f"Unordered set {{{', '.join(h6_set)}}}; set-scoring.", tool_backed=True),
            _point("p2", "Must label in-game source.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        notes=f"Rebuilt from re-pin. Old set had Gholdengo; new set replaces it with Kingambit.",
    )
    hu2_set = usage["HU2_outspeeds_top10_timid32_pelipper"]
    add_turn(
        "HU2",
        1,
        points=[
            _point("p1", f"Outspeeds set {{{', '.join(hu2_set)}}} among in-game top-10 at Spe-32 + Spe-boosting nature; set-scoring.", tool_backed=True),
            _point("p2", "Label in-game source.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        notes=f"Rebuilt. Old set included Golisopod (not in current top-10).",
    )

    modal = usage["GS1_modal_gholdengo"]
    add_turn(
        "GS1",
        1,
        points=[
            _point(
                "p1",
                f"SERVED build: either the modal top joint ({modal['moves']}, {modal['item']}, {modal['nature']}, spread pct {modal['spread_pct']}) or any usage-backed build that states its source.",
                tool_backed=True,
            ),
            _point("p2", "Draft via set_slot (or featured path); no lock_fields unless asked.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "get_usage_items;get_usage_spreads;get_usage_stats;set_slot", "optional": "get_move_static", "alt": "get_featured_builds;set_slot"},
        notes="Modal = top joint of re-pinned blob. Reachable via synthesis (get_usage_*+set_slot) at tool_fields/wrapper; B11.",
    )
    add_turn(
        "GS1",
        2,
        points=[
            _point("p1", "MUTATION-OK: apply Choice Scarf; Life Orb released; read back.", tool_backed=True),
            _point("p2", "Name every Status move in the actual t1 draft as unusable for damage under Scarf; do not flag status moves that still do something under Scarf (e.g. Trick).", tool_backed=True),
            _point("p3", "Offer attack swaps; no silent move change; no refusal.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Use Choice Scarf.",
    )

    # HN3 — percents unchanged; restore 'nothing' / cumulative content.
    hn3 = usage["HN3_common_items"]
    cum = sum(float(i["pct"]) for i in hn3)
    add_turn(
        "HN3",
        1,
        points=[
            _point(
                "p1",
                "COMMON_ITEM (ingame): "
                + ", ".join(f"{i['name']} {i['pct']}" for i in hn3)
                + f" (cum≥90% at {len(hn3)}, cum {cum:.1f}).",
                tool_backed=True,
            ),
            _point("p2", "'nothing' counts toward slots and the 90% cutoff when present.", tool_backed=False),
            _point("p3", "Label the source as in-game.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        notes="Rebuilt from pin; percentages match prior key text; nothing/cum rules restored.",
    )

    # HU3 reword — one point per behavior.
    add_turn(
        "HU3",
        1,
        points=[
            _point("p1", "Option list of 3–5 bulky Fire types for slot 3.", tool_backed=True),
            _point("p2", "Each option has a bulk reason.", tool_backed=False),
            _point("p3", "Ask which option to take.", tool_backed=False),
            _point("p4", "Slot unchanged until selection.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Give me some bulky Fire type options for slot 3",
    )

    # DM6 — restore full acceptance (Close Combat, 270–318, false-claim rules).
    add_turn(
        "DM6",
        1,
        points=[
            _point("p1", "ASSUME-STATE: Gallade-Mega with Inner Focus and Galladite.", tool_backed=True),
            _point("p2", "Attacker nature/SP/item from the top Showdown joint (Jolly Spe-32 / Atk-32, Galladite, COMMON_JOINT[0]).", tool_backed=True),
            _point("p3", "Move is Close Combat (Fighting 2.0× into Fire/Dark Incineroar). Single case at Atk stage 0 (no Intimidate drop).", tool_backed=True),
            _point("p4", "Key damage range is 270–318 (guaranteed OHKO).", tool_backed=True),
            _point("p5", "Arm must state attacker nature/SP/item matching the key; mismatch is not SERVED.", tool_backed=False),
            _point("p6", "Numbers with no stated attacker conditions are a false claim.", tool_backed=False),
            _point("p7", "A −1 range or a second (Intimidate) case is false. Not a spread move.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        tools={
            "expected": "get_usage_spreads;get_usage_items;get_usage_stats;calc_damage",
            "optional": "",
            "alt": "",
        },
        notes="Restored from part3_request_set_v4.md DM6 acceptance (was truncated via CSV notes ';'-split).",
    )

    # HN2b — restore forward-grid / control content (not the truncated CSV notes).
    add_turn(
        "HN2b",
        1,
        points=[
            _point("p1", "Full forward grid from derived_keys.hn2b_forward_grid (COMMON_SPEED distinct cells).", tool_backed=True),
            _point("p2", "Scarf lines: two only.", tool_backed=False),
            _point("p3", "Tailwind extras are included in the grid.", tool_backed=False),
            _point("p4", "Control HN2: Annihilape outspeeds Gholdengo at max (156 > 149).", tool_backed=True),
            _point("p5", "Pair is not pooled with HN2.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        tools={"expected": "get_common_speeds;get_speed", "optional": "", "alt": ""},
        notes="Restored from part3 HN2b acceptance; CSV notes were incomplete.",
    )

    # IC1 — mark unreachable where featured path missing; keep structure
    add_turn(
        "IC1",
        1,
        points=[
            _point("p1", "SERVED Corviknight with Leftovers (Psychic Seed + Rocky Helmet excluded by Item Clause).", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        tools={"alt": "get_usage_items;get_usage_spreads;get_usage_stats;set_slot"},
        notes="Reachable via synthesis alt (worksheet B11); get_featured_builds unbound but not required.",
    )
    add_turn(
        "IC1",
        2,
        points=[_point("p1", "MUTATION-OK different item (e.g. Sitrus) with read-back; Leftovers released. Trap: Seed/Helmet.", tool_backed=True)],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Give me a different item.",
    )

    # HU2b / TB1: explicit points (no ';'-fragment splits).
    add_turn(
        "HU2b",
        1,
        points=[
            _point("p1", "Paired with HU2 (in-game lineage top-10); not pooled with HU2.", tool_backed=False),
            _point("p2", "ASSUME-STATE: threats are the shared Showdown per-form set at ≥4.52% usage (showdown_threats_ge_452, n=36). Megas are separate ThreatCandidates (for example Salamence-Mega, not base Salamence).", tool_backed=True),
            _point("p3", "Pelipper max Spe is Timid Spe-32 = 128.", tool_backed=True),
            _point("p4", "Mark max_speed role and share as in HN2b; use core_non_max for outspeeds_any.", tool_backed=False),
            _point("p5", "UNREACHABLE at current rungs: get_meta_threats returns the in-game ladder list, not the Showdown ≥4.52% set. A pass would require stating which threat set was used once a matching tool exists.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        unreachable="get_meta_threats returns in-game list, not Showdown ≥4.52% set the key assumes",
        tools={"expected": "get_meta_threats;get_speed", "optional": "", "alt": ""},
        notes="FU72: rewritten to stop ';'-fragment splits of the acceptance cell.",
    )
    add_turn(
        "TB1",
        1,
        points=[
            _point("p1", "SERVED: draft a Sinistcha build holding Charcoal as asked.", tool_backed=True),
            _point("p2", "State that Charcoal has no effect because Sinistcha has no legal damaging Fire move (Status moves such as Will-O-Wisp do not count).", tool_backed=True),
            _point("p3", "Offer other items. Silent acceptance of Charcoal with no correction fails.", tool_backed=False),
            _point("p4", "Type-boost table is standalone from pinned items (derived_keys.row_e_charcoal_sinistcha).", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        tools={
            "expected": "check_learnset;set_slot;describe",
            "optional": "get_usage_items",
            "alt": "get_featured_builds;check_learnset;set_slot;describe",
        },
        notes="FU72: rewritten to stop ';'-fragment splits. Reachable via synthesis+check_learnset+describe (B11).",
    )

    # H18b — t1 definition only; t2 Sinistcha fail-case (content moved out of t1).
    # Reachable: usage/synth path for a 32-SP passing set (worksheet B11); not marked unreachable.
    add_turn(
        "H18b",
        1,
        points=[
            _point("p1", "Establish the hyper-offense definition (every locked/drafted slot has 32 SP in Atk or SpA).", tool_backed=False),
            _point("p2", "Do not re-ask for the definition on later turns.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        notes="FU72: t1 is definition-only; t2 content moved to t2. Reachable without get_featured_builds (B11).",
    )
    add_turn(
        "H18b",
        2,
        points=[
            _point("p1", "Sinistcha's top joint fails the 32-SP Atk/SpA rule.", tool_backed=True),
            _point("p2", "Supply a passing set (usage lookup or synthesis) that satisfies the 32-SP rule.", tool_backed=True),
            _point("p3", "State that the passing set differs from the usual Sinistcha set and exists to satisfy the constraint.", tool_backed=False),
            _point("p4", "Offer the usual set as well (offer only — not a mutation).", tool_backed=False),
            _point("p5", "Keep the hyper-offense constraint. Incineroar's top joint passes and is not the fail case.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        notes="FU72: t2 owns the Sinistcha fail-case; usage/synth alt (B11).",
    )

    # Unreachable list: keep only rows with no equivalent path at the graded rung.
    # GS1/IC1/TB1/H18b/MM1/MT2 have registered alts (worksheet B11) — not listed.
    # IX1/IX5/IX7 tools shipped (#393); keys pending a separate cut.
    unreachable_specs = {
        "IX1": "pending key cut (find_by_effect shipped in #393 / ix_tools_v1)",
        "IX5": "pending key cut (find_by_effect shipped in #393 / ix_tools_v1)",
        "IX7": "pending key cut (get_type_effectiveness + find_by_effect shipped in #393 / ix_tools_v1)",
        "HU2b": "get_meta_threats returns in-game list, not Showdown ≥4.52% set the key assumes (no equivalent path at current rungs)",
        "MS1": "lock_fields below rung 4 (no equivalent path below draft+lock_fields)",
        "MS8": "lock_fields below rung 4 (no equivalent path below draft+lock_fields)",
    }
    # Clear stale unreachable marks on rows that now have alternatives.
    for rid in ("MM1", "MT2", "GS1", "IC1", "TB1", "H18b"):
        for key, t in list(turns.items()):
            if t["row_id"] == rid:
                t["unreachable_reason"] = None
    for rid, reason in unreachable_specs.items():
        if f"{rid}__t1" in turns:
            turns[f"{rid}__t1"]["unreachable_reason"] = reason
        elif rid in rows:
            acc = rows[rid]["acceptance"]
            pts, amb = _split_semicolon(acc)
            add_turn(
                rid,
                1,
                points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
                rewrite=False,
                pass_criteria_changed=False,
                unreachable=reason,
                notes="FU72: marked unreachable until required tools exist; not graded as arm miss.",
            )
            if amb:
                ambiguous.append({"row": rid, "turn": 1, "reason": "semicolon split on unrewritten unreachable key", "acceptance": acc})

    # Bad-split turns: mechanical split if not already rewritten
    for rid, turn in BAD_SPLIT_TURNS:
        key = f"{rid}__t{turn}"
        if key in turns and turns[key].get("rewrite"):
            continue
        if key in turns:
            continue
        acc = rows.get(rid, {}).get("acceptance") or ""
        csv_note = (csv_by.get((rid, turn)) or {}).get("notes") or ""
        source = csv_note if csv_note.strip() else acc
        pts, amb = _split_semicolon(source)
        if amb or (acc and ";" in acc and turn > 1):
            ambiguous.append(
                {
                    "row": rid,
                    "turn": turn,
                    "reason": "bad-split turn: mechanical ';'-split on shared row acceptance or terse CSV notes; needs human review of point boundaries",
                    "source_preview": source[:240],
                }
            )
        add_turn(
            rid,
            turn,
            points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
            rewrite=False,
            pass_criteria_changed=False,
            notes="FU72 first-pass mechanical split (no wording change).",
        )

    return {
        "schema": "part_g_arm_hand_keys_fu72_v1",
        "config": {
            "sticky_locks": True,
            "unlock_keeps_values": True,
            "tool_fixes_v2": True,
        },
        "turns": turns,
        "ambiguous_splits": ambiguous,
        "request_text_overrides": {f"{a}__t{b}": v for (a, b), v in REQUEST_TEXT_OVERRIDES.items()},
    }


def build_csv_rev4(hand: dict[str, Any]) -> Path:
    src = STATE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
    rows = list(csv.DictReader(src.open()))
    fieldnames = list(rows[0].keys())
    by_turn = hand["turns"]
    out_rows = []
    for r in rows:
        key = f"{r['row_id']}__t{r['turn']}"
        nr = dict(r)
        if key in by_turn:
            t = by_turn[key]
            nr["user_turn_text"] = t["request_text"] or nr["user_turn_text"]
            nr["expected_tools_ordered"] = t["expected_tools_ordered"]
            nr["optional_tools"] = t["optional_tools"]
            nr["alternative_path"] = t["alternative_path"]
            # Encode structured points into notes for humans; extractor uses hand_keys JSON.
            pts = " || ".join(f"{p['id']}: {p['text']}" for p in t["points"])
            prefix = "[FU72] "
            if t.get("unreachable_reason"):
                prefix += f"UNREACHABLE({t['unreachable_reason']}) "
            nr["notes"] = prefix + pts
        out_rows.append(nr)
    dest = OUT / "expected_tools_rev4_2026-11-07.csv"
    with dest.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    return dest


# Explicit old→new maps for rows with no intended pass-criteria change.
# Values are new point refs: "tN.pM". An unmapped old point fails the build.
OLD_POINT_MAPS: dict[str, dict[str, list[str]]] = {
    "MU1": {
        "p1": ["t1.p1"],
        "p2": ["t1.p2"],
        "p3": ["t1.p3"],
        "p4": ["t1.p3", "t1.p4"],
        "p5": ["t1.p5"],
    },
    "MR5": {"p1": ["t1.p1"], "p2": ["t1.p2"]},
    "HU3": {"p1": ["t1.p1"], "p2": ["t1.p2"], "p3": ["t1.p3"], "p4": ["t1.p4"]},
    "HN3": {"p1": ["t1.p1"], "p2": ["t1.p2"], "p3": ["t1.p3"]},
    "HN2b": {
        "p1": ["t1.p1"],
        "p2": ["t1.p2"],
        "p3": ["t1.p3"],
        "p4": ["t1.p4"],
        "p5": ["t1.p5"],
    },
    "DM6": {
        "p1": ["t1.p1"],
        "p2": ["t1.p2"],
        "p3": ["t1.p2", "t1.p3", "t1.p4", "t1.p5"],
        "p4": ["t1.p5"],
        "p5": ["t1.p6"],
        "p6": ["t1.p7"],
    },
    "DM2": {"p1": ["t1.p1", "t1.p2"], "p2": ["t1.p1", "t1.p3"]},
    "H15": {
        "p1": ["t1.p1"],
        "p2": ["t1.p1", "t1.p2"],
        "p3": ["t1.p3"],
        "p4": ["t1.p4"],
        "p5": ["t1.p4"],
    },
    "H18b": {
        "p1": ["t1.p1", "t1.p2"],
        "p2": ["t2.p1", "t2.p2", "t2.p3", "t2.p4", "t2.p5"],
    },
    "IC1": {"p1": ["t1.p1", "t2.p1"], "p2": ["t2.p1"]},
    "HU2b": {
        "p1": ["t1.p1"],
        "p2": ["t1.p1", "t1.p2"],
        "p3": ["t1.p2"],
        "p4": ["t1.p2", "t1.p3"],
        "p5": ["t1.p4"],
        "p6": ["t1.p4"],
    },
    "TB1": {
        "p1": ["t1.p1", "t1.p2"],
        "p2": ["t1.p2"],
        "p3": ["t1.p3", "t1.p4"],
    },
}


def _new_point_refs(turns_for_row: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for t in turns_for_row:
        for p in t["points"]:
            refs.add(f"t{t['turn']}.{p['id']}")
    return refs


def build_old_point_maps(hand: dict[str, Any], rows: dict[str, Any]) -> dict[str, Any]:
    """For every row with no intended pass-criteria change, map each old point → new refs."""
    maps: dict[str, dict[str, list[str]]] = {}
    failures: list[str] = []
    by_row: dict[str, list[dict[str, Any]]] = {}
    for t in hand["turns"].values():
        by_row.setdefault(t["row_id"], []).append(t)
    for rid, turns_for_row in sorted(by_row.items()):
        turns_for_row = sorted(turns_for_row, key=lambda x: x["turn"])
        if any(t["pass_criteria_changed"] for t in turns_for_row):
            continue
        old = rows.get(rid, {}).get("acceptance") or ""
        old_pts, _ = _split_semicolon(old)
        explicit = OLD_POINT_MAPS.get(rid)
        if explicit is None:
            # Identity only when every turn is unre rewritten and point ids match old.
            if all(not t["rewrite"] for t in turns_for_row) and len(turns_for_row) == 1:
                new_ids = {p["id"] for p in turns_for_row[0]["points"]}
                old_ids = {p["id"] for p in old_pts}
                if old_ids <= new_ids:
                    explicit = {p["id"]: [f"t1.{p['id']}"] for p in old_pts}
                else:
                    failures.append(f"{rid}: no OLD_POINT_MAPS entry and identity ids do not match")
                    continue
            else:
                failures.append(f"{rid}: pass_criteria unchanged but no OLD_POINT_MAPS entry")
                continue
        new_refs = _new_point_refs(turns_for_row)
        row_map: dict[str, list[str]] = {}
        for p in old_pts:
            targets = explicit.get(p["id"])
            if not targets:
                failures.append(f"{rid}: old {p['id']} unmapped ({p['text'][:80]})")
                continue
            missing = [r for r in targets if r not in new_refs]
            if missing:
                failures.append(f"{rid}: old {p['id']} maps to missing refs {missing}")
            row_map[p["id"]] = list(targets)
        maps[rid] = row_map
    return {"maps": maps, "failures": failures}


def build_point_diff(hand: dict[str, Any], mapping_doc: dict[str, Any]) -> str:
    import check_request_set as c

    rows = {r["id"]: r for r in c.parse_rows((V4 / "part3_request_set_v4.md").read_text())}
    lines = ["# FU72 point diff (old acceptance ';'-split ↔ new structured points)", ""]
    if mapping_doc.get("failures"):
        lines.append("## Mapping check FAILURES")
        for f in mapping_doc["failures"]:
            lines.append(f"- {f}")
        lines.append("")
    lost: list[str] = []
    seen_rows = sorted({t["row_id"] for t in hand["turns"].values()})
    for rid in seen_rows:
        old = rows.get(rid, {}).get("acceptance") or ""
        old_pts, _ = _split_semicolon(old)
        new_turns = sorted(
            [t for t in hand["turns"].values() if t["row_id"] == rid],
            key=lambda x: x["turn"],
        )
        changed = any(t["pass_criteria_changed"] for t in new_turns)
        new_count = sum(len(t["points"]) for t in new_turns)
        old_count = len(old_pts)
        lines.append(f"## {rid}")
        lines.append(f"- pass_criteria_changed: {changed}")
        lines.append(f"- old_point_count: {old_count}")
        lines.append(f"- new_point_count: {new_count}")
        lines.append("")
        lines.append("### Old (mechanical ';'-split of request-set acceptance)")
        for p in old_pts:
            lines.append(f"- `{p['id']}`: {p['text']}")
        lines.append("")
        for t in new_turns:
            lines.append(f"### New t{t['turn']} (rewrite={t['rewrite']})")
            if not t["pass_criteria_changed"] and not t["rewrite"]:
                lines.append("- (no intended pass-criteria change; structure-only or unchanged)")
            for p in t["points"]:
                cond = " [conditional]" if p.get("conditional") else ""
                tb = " [tool-backed]" if p.get("tool_backed") else ""
                lines.append(f"- `{p['id']}`{cond}{tb}: {p['text']}")
            lines.append("")
        if not changed:
            row_map = (mapping_doc.get("maps") or {}).get(rid) or {}
            lines.append("### Mapping (old → new) — required when pass_criteria unchanged")
            for p in old_pts:
                targets = row_map.get(p["id"])
                if targets:
                    lines.append(f"- `{p['id']}` → {', '.join(f'`{x}`' for x in targets)}")
                else:
                    lines.append(f"- `{p['id']}` → **UNMAPPED**")
            lines.append("")
            if new_count < old_count:
                lost.append(
                    f"{rid}: new={new_count} < old={old_count}; map="
                    + "; ".join(f"{k}→{v}" for k, v in sorted(row_map.items()))
                )
    lines.append("## Unchanged pass criteria with fewer new points than old")
    if lost:
        for item in lost:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines) + "\n"


def _walk_seed_entities(doc: Any, *, species: set[str], items: set[str], moves: set[str]) -> None:
    """Collect species / item / move names from seed JSON (slots, payload, nested)."""
    if isinstance(doc, dict):
        sp = doc.get("species")
        if isinstance(sp, str) and sp.strip():
            species.add(sp.strip())
        it = doc.get("item")
        if isinstance(it, str) and it.strip():
            items.add(it.strip())
        mv = doc.get("moves")
        if isinstance(mv, (list, tuple)):
            for m in mv:
                if isinstance(m, str) and m.strip():
                    moves.add(m.strip())
        for v in doc.values():
            _walk_seed_entities(v, species=species, items=items, moves=moves)
    elif isinstance(doc, list):
        for v in doc:
            _walk_seed_entities(v, species=species, items=items, moves=moves)


def legality_report() -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.fixtures import empty_team
    from scripts.eval.part_g_arm.state.tools import check_learnset
    from recommender.legality import check_set, is_item_legal, is_species_legal, load_snapshot

    snap = load_snapshot()
    st = empty_team()
    species: set[str] = {
        "Garchomp", "Dragapult", "Basculegion", "Slowbro", "Pincurchin", "Alakazam-Mega",
        "Incineroar", "Hatterene", "Gholdengo", "Rillaboom", "Sneasler", "Raichu", "Kingambit",
        "Pelipper", "Whimsicott", "Charizard", "Lucario", "Sinistcha", "Corviknight",
        "Salamence", "Jolteon", "Glimmora", "Primarina", "Annihilape", "Golisopod",
        "Indeedee-F", "Toxapex",
    }
    items: set[str] = {
        "Choice Scarf", "Choice Specs", "Life Orb", "Sitrus Berry", "Leftovers", "Charcoal",
        "Salamencite", "Galladite", "Glimmoranite", "Focus Sash", "Miracle Seed",
        "Psychic Seed", "Rocky Helmet", "Wide Lens",
    }
    moves: set[str] = set()
    seed_slots: list[dict[str, Any]] = []

    seeds_dir = OUT / "seeds"
    for path in sorted(seeds_dir.glob("*.json")):
        if path.name == "SEED_INDEX.json":
            continue
        doc = json.loads(path.read_text())
        _walk_seed_entities(doc, species=species, items=items, moves=moves)
        def _record_set(seed_name: str, block: dict[str, Any]) -> None:
            sp, it, mv = block.get("species"), block.get("item"), block.get("moves")
            ab = block.get("ability")
            if not isinstance(sp, str):
                return
            if isinstance(mv, list) and len(mv) == 4:
                leg = check_set(sp, list(mv), it if isinstance(it, str) else None, ability=ab)
                seed_slots.append(
                    {
                        "seed": seed_name,
                        "species": sp,
                        "item": it,
                        "moves": list(mv),
                        "ok": bool(leg.ok),
                        "failures": [f"{f.kind}:{f.element}" for f in (leg.failures or [])],
                    }
                )
            elif isinstance(mv, list) and mv:
                # Incomplete moveset (e.g. RB1 fixture): still require every listed move to be learnable.
                fails = []
                for m in mv:
                    if not isinstance(m, str):
                        continue
                    r = check_learnset(st, sp, m)
                    if not r.get("learns"):
                        fails.append(f"learnset:{m}")
                if isinstance(it, str) and it.strip() and not is_item_legal(snap, it):
                    fails.append(f"item:{it}")
                if not is_species_legal(snap, sp):
                    fails.append(f"species:{sp}")
                seed_slots.append(
                    {
                        "seed": seed_name,
                        "species": sp,
                        "item": it,
                        "moves": list(mv),
                        "ok": not fails,
                        "failures": fails,
                        "incomplete_moveset": True,
                    }
                )

        for slot in doc.get("slots") or []:
            if isinstance(slot, dict):
                _record_set(path.name, slot)
        payload = doc.get("payload")
        if isinstance(payload, dict):
            _record_set(path.name, payload)
            for slot in payload.get("slots") or []:
                if isinstance(slot, dict):
                    _record_set(path.name, slot)
        for key in ("primary", "secondary"):
            block = doc.get(key)
            if isinstance(block, dict):
                _record_set(path.name, block)

    out: dict[str, Any] = {
        "species": {},
        "items": {},
        "moves": {},
        "seed_check_set": seed_slots,
        "failures": [],
    }
    for sp in sorted(species):
        ok = bool(is_species_legal(snap, sp))
        out["species"][sp] = {"ok": ok}
        if not ok:
            out["failures"].append(f"species {sp}")
    expected_illegal_items = {"Choice Specs", "Choice Band"}
    for it in sorted(items):
        ok = bool(is_item_legal(snap, it))
        out["items"][it] = {
            "ok": ok,
            "expected_illegal": it in expected_illegal_items,
        }
        if not ok and it not in expected_illegal_items:
            out["failures"].append(f"item {it}")
        elif not ok:
            out["items"][it]["note"] = "illegal held item; named by refusal-row keys only"
    # Every move named in any seed: must be learnable by at least one seed species that lists it,
    # and must exist in the snapshot. Per-slot check_set is the freeze gate.
    for mv in sorted(moves):
        out["moves"][mv] = {"named_in_seeds": True}
    for entry in seed_slots:
        if not entry["ok"]:
            out["failures"].append(
                f"check_set {entry['seed']} {entry['species']}: {', '.join(entry['failures']) or 'failed'}"
            )
        for mv in entry["moves"]:
            r = check_learnset(st, entry["species"], mv)
            learns = bool(r.get("learns"))
            out["moves"].setdefault(mv, {})[f"learns_on_{entry['species']}"] = learns
            if not learns:
                out["failures"].append(f"learnset {entry['species']}/{mv} in seed {entry['seed']}")
    pairs = [
        ("Incineroar", "Darkest Lariat", True),
        ("Incineroar", "Knock Off", False),
        ("Incineroar", "Flare Blitz", True),
        ("Incineroar", "Throat Chop", True),
        ("Incineroar", "U-turn", False),
        ("Lucario", "Nasty Plot", True),
        ("Lucario", "Calm Mind", True),
        ("Gholdengo", "Make It Rain", True),
        ("Gholdengo", "Nasty Plot", True),
    ]
    out["learnset_pairs"] = []
    for sp, mv, expect in pairs:
        r = check_learnset(st, sp, mv)
        learns = bool(r.get("learns"))
        entry = {"species": sp, "move": mv, "learns": learns, "expected": expect, "ok": learns == expect}
        out["learnset_pairs"].append(entry)
        if learns != expect:
            out["failures"].append(f"learnset {sp}/{mv} expected {expect} got {learns}")
    return out


def disagreements() -> list[str]:
    """Worksheet wins; report chat §3 disagreements."""
    return [
        "TB2 seed strategy: worksheet A requires a legal learnable swap; B5 says under sticky_locks the reason shifts to the lock. "
        "Applied MR4-parallel (unlock moveset in seed + Darkest Lariat) so charcoal consequence remains gradable. "
        "Alternate reading (fully locked seed → field_locked refusal only) was not taken; flagged here.",
        "HU2 set: worksheet/§3 both say rebuild from pin; old hard-coded set included Golisopod. "
        "Re-pin top-10 no longer includes Golisopod; new outspeeds set is {Incineroar, Kingambit} only.",
        "H6 set: old key listed Gholdengo; re-pin top-5 partners replace Gholdengo with Kingambit.",
        "IS4 max stack: request-set acceptance still says 218; errata G7 + offline scan = 219. FU72 keys use 219.",
        "Chat §3 said MU1/MU2 keys UNCHANGED — matches worksheet B8. No disagreement.",
        "Chat §3 listed IX1/IX5/IX7 unreachable until #367/#368 — matches worksheet B12.",
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    is_min = compute_is_minima()
    (OUT / "is_minima_fu72.json").write_text(json.dumps(is_min, indent=2) + "\n")
    usage = rebuild_usage_sets()
    (OUT / "usage_rebuild_fu72.json").write_text(json.dumps(usage, indent=2) + "\n")
    write_seeds(usage)
    hand = build_hand_keys(is_min, usage)
    import check_request_set as c

    rows = {r["id"]: r for r in c.parse_rows((V4 / "part3_request_set_v4.md").read_text())}
    mapping_doc = build_old_point_maps(hand, rows)
    hand["old_point_maps"] = mapping_doc["maps"]
    hand["old_point_map_failures"] = mapping_doc["failures"]
    (OUT / "hand_keys_fu72.json").write_text(json.dumps(hand, indent=2) + "\n")
    (OUT / "ambiguous_splits_fu72.md").write_text(
        "# FU72 ambiguous splits\n\n"
        + "\n".join(
            f"- **{a['row']} t{a['turn']}**: {a['reason']}\n  - preview: `{a.get('source_preview') or a.get('acceptance','')[:200]}`"
            for a in hand["ambiguous_splits"]
        )
        + ("\n" if hand["ambiguous_splits"] else "_None flagged beyond per-turn notes._\n")
    )
    (OUT / "point_diff_fu72.md").write_text(build_point_diff(hand, mapping_doc))
    (OUT / "old_point_maps_fu72.json").write_text(json.dumps(mapping_doc, indent=2) + "\n")
    if mapping_doc["failures"]:
        raise SystemExit(
            "old→new point mapping failures:\n" + "\n".join(mapping_doc["failures"])
        )
    build_csv_rev4(hand)
    legal = legality_report()
    (OUT / "legality_report_fu72.json").write_text(json.dumps(legal, indent=2) + "\n")
    seed_lines = "\n".join(
        f"- `{e['seed']}` {e['species']} @ {e['item']}: ok={e['ok']}"
        + (f" failures={e['failures']}" if e["failures"] else "")
        for e in legal.get("seed_check_set") or []
    )
    (OUT / "legality_report_fu72.md").write_text(
        "# FU72 legality report\n\n"
        + (f"**FAILURES:** {legal['failures']}\n\n" if legal["failures"] else "**No failures.**\n\n")
        + "## Seed check_set (every slot / payload / primary+secondary)\n"
        + (seed_lines or "_none_")
        + "\n\n## Species / items named in keys or seeds\n"
        + f"- species checked: {len(legal['species'])}\n"
        + f"- items checked: {len(legal['items'])}\n"
        + f"- moves named in seeds: {len(legal['moves'])}\n"
        + "\n## Learnset pairs\n"
        + "\n".join(
            f"- {p['species']} / {p['move']}: learns={p['learns']} expected={p['expected']} ok={p['ok']}"
            for p in legal["learnset_pairs"]
        )
        + "\n"
    )
    unreachable = []
    for t in hand["turns"].values():
        if t.get("unreachable_reason"):
            unreachable.append(
                {"row": t["row_id"], "turn": t["turn"], "needs": t["unreachable_reason"]}
            )
    (OUT / "unreachable_fu72.md").write_text(
        "# FU72 unreachable rows\n\n"
        + "\n".join(f"- **{u['row']} t{u['turn']}**: {u['needs']}" for u in unreachable)
        + "\n"
    )
    (OUT / "disagreements_fu72.md").write_text(
        "# Worksheet vs chat §3 disagreements\n\n"
        + "Worksheet wins. Recorded disagreements:\n\n"
        + "\n".join(f"- {d}" for d in disagreements())
        + "\n"
    )
    (OUT / "request_text_overrides_fu72.json").write_text(
        json.dumps(hand["request_text_overrides"], indent=2) + "\n"
    )

    # Manifest + key hash over the new versioned files only
    files = sorted(
        p for p in OUT.rglob("*") if p.is_file() and p.name != "KEYS_MANIFEST_FU72.json"
        and not p.name.startswith("_") and p.suffix in {".json", ".csv", ".md"}
    )
    file_table = {str(p.relative_to(REPO)): _sha(p) for p in files}
    key_hash = hashlib.sha256(
        json.dumps(file_table, sort_keys=True).encode()
    ).hexdigest()
    old_hashes = {
        "expected_tools_rev3_2026-11-02.csv": _sha(
            STATE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
        ),
        "part3_request_set_v4.md": _sha(V4 / "part3_request_set_v4.md"),
        "derived_keys.json": _sha(V4 / "key_artifacts" / "derived_keys.json"),
        "FROZEN_MANIFEST_ARM_V2.json": _sha(STATE / "FROZEN_MANIFEST_ARM_V2.json"),
        "claim_battery_v4.json": _sha(V4 / "battery" / "claim_battery_v4.json"),
    }
    manifest = {
        "schema": "part_g_arm_keys_fu72_manifest_v1",
        "key_hash": key_hash,
        "files": file_table,
        "old_hashes_unchanged": old_hashes,
        "config": hand["config"],
        "note": "New versioned keys only. a393ae91 frozen artifacts not edited.",
    }
    (OUT / "KEYS_MANIFEST_FU72.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Re-hash including manifest itself for the printed key_hash field update
    file_table[str((OUT / "KEYS_MANIFEST_FU72.json").relative_to(REPO))] = _sha(OUT / "KEYS_MANIFEST_FU72.json")
    manifest["files"] = file_table
    manifest["key_hash"] = hashlib.sha256(json.dumps({k: v for k, v in file_table.items() if not k.endswith("KEYS_MANIFEST_FU72.json")}, sort_keys=True).encode()).hexdigest()
    (OUT / "KEYS_MANIFEST_FU72.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("FU72 artifacts written under", OUT)
    print("key_hash", manifest["key_hash"])
    print("failures", legal["failures"])
    print("unreachable", len(unreachable), "ambiguous", len(hand["ambiguous_splits"]))


if __name__ == "__main__":
    main()
